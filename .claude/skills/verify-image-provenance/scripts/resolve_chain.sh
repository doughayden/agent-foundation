#!/usr/bin/env bash
# Resolve and verify the image digest chain for a Cloud Run service.
#
# Modes:
#   --service NAME              Full chain: service -> index -> amd64 child vs revision (default mode)
#   --revision NAME             Print the platform digest a revision runs
#   --compare REV_A REV_B       Compare the platform digests of two revisions
#   --tag TAG                   Resolve a tag to its index digest and list children
#   --find-commit DIGEST        Find which {sha}-tagged index contains a platform digest
#   --classify DIGEST           Identify what a digest is: index, platform image,
#                               attestation (and what it attests), or buildcache
#
# Common flags: --project ID --region REGION --repo-uri REGISTRY/REPO/IMAGE
# Registry modes derive the repo URI from --service when --repo-uri is omitted.
# Requires: gcloud, docker (buildx), jq
set -euo pipefail

PROJECT="" REGION="" SERVICE="" REVISION="" TAG="" FIND_DIGEST="" REPO_URI=""
COMPARE_A="" COMPARE_B="" CLASSIFY_DIGEST=""
MODE="service"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --service) SERVICE="$2"; shift 2 ;;
    --revision) REVISION="$2"; MODE="revision"; shift 2 ;;
    --compare) COMPARE_A="$2"; COMPARE_B="$3"; MODE="compare"; shift 3 ;;
    --tag) TAG="$2"; MODE="tag"; shift 2 ;;
    --find-commit) FIND_DIGEST="$2"; MODE="find-commit"; shift 2 ;;
    --classify) CLASSIFY_DIGEST="$2"; MODE="classify"; shift 2 ;;
    --repo-uri) REPO_URI="$2"; shift 2 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done

[[ -n "$PROJECT" && -n "$REGION" ]] || { echo "--project and --region are required" >&2; exit 2; }

validate_digest() {
  [[ "$1" =~ ^sha256:[0-9a-f]{64}$ ]] \
    || { echo "error: invalid digest format: $1 (expected sha256:<64 hex chars>)" >&2; exit 2; }
}

run_gcloud() { gcloud "$@" --project "$PROJECT" 2>/dev/null; }

revision_platform_digest() {
  local img
  img=$(run_gcloud run revisions describe "$1" --region "$REGION" \
    --format 'value(spec.containers[0].image)') && [[ -n "$img" ]] \
    || { echo "error: could not describe revision $1 (check name, project, region)" >&2; exit 1; }
  echo "$img"
}

service_image() {
  local img
  img=$(run_gcloud run services describe "$1" --region "$REGION" \
    --format 'value(spec.template.spec.containers[0].image)') && [[ -n "$img" ]] \
    || { echo "error: could not describe service $1 (check name, project, region)" >&2; exit 1; }
  echo "$img"
}

# jq: render one index child as "<platform|attestation>: <digest>"
JQ_CHILDREN='.manifests[] |
  (if (.annotations["vnd.docker.reference.type"] // "") == "attestation-manifest"
   then "attestation"
   else ((.platform.os // "?") + "/" + (.platform.architecture // "?")) end)
  + ": " + .digest'

# jq: extract the amd64 child digest of an index ("" when absent)
JQ_AMD64='[.manifests[]? | select(.platform.architecture == "amd64")][0].digest // ""'

# Registry modes derive the repo URI from --service when --repo-uri is omitted
if [[ -z "$REPO_URI" && -n "$SERVICE" && "$MODE" != "service" ]]; then
  REPO_URI=$(service_image "$SERVICE" | cut -d'@' -f1)
fi

case "$MODE" in
  revision)
    IMG=$(revision_platform_digest "$REVISION")
    echo "revision: $REVISION"
    echo "platform_image: $IMG"
    echo "repo_uri: ${IMG%@*}"
    ;;

  compare)
    A=$(revision_platform_digest "$COMPARE_A" | sed 's/.*@//')
    B=$(revision_platform_digest "$COMPARE_B" | sed 's/.*@//')
    echo "revision_a: $COMPARE_A -> $A"
    echo "revision_b: $COMPARE_B -> $B"
    if [[ "$A" == "$B" ]]; then
      echo "verdict: IDENTICAL - both revisions run the same platform image"
    else
      echo "verdict: DIFFERENT - revisions run different platform images"
    fi
    ;;

  tag)
    [[ -n "$REPO_URI" ]] || { echo "pass --service or --repo-uri for --tag mode" >&2; exit 2; }
    INDEX=$(run_gcloud artifacts docker images describe "${REPO_URI}:${TAG}" \
      --format 'value(image_summary.digest)')
    echo "tag: $TAG"
    echo "index_digest: $INDEX"
    echo "children:"
    docker buildx imagetools inspect "${REPO_URI}@${INDEX}" --raw | jq -r "$JQ_CHILDREN" | sed 's/^/  /'
    echo "note: the artifact shown as platform unknown/unknown in registry UIs is the attestation child above (BuildKit provenance), never the index and never a broken image"
    ;;

  find-commit)
    validate_digest "$FIND_DIGEST"
    [[ -n "$REPO_URI" ]] || { echo "pass --service or --repo-uri for --find-commit mode" >&2; exit 2; }
    echo "searching tagged indexes for platform digest: $FIND_DIGEST"
    FOUND=""
    while read -r T D; do
      [[ "$T" =~ ^(latest|buildcache|pr-.*)$ ]] && continue
      CHILD=$(docker buildx imagetools inspect "${REPO_URI}@${D}" --raw 2>/dev/null | jq -r "$JQ_AMD64" || true)
      if [[ "$CHILD" == "$FIND_DIGEST" ]]; then
        echo "match: tag=$T index=$D"
        FOUND=1
      fi
    done < <(run_gcloud artifacts docker tags list "$REPO_URI" \
      --format 'value(tag.basename(), version.basename())')
    [[ -n "$FOUND" ]] || { echo "no tagged index contains $FIND_DIGEST"; exit 1; }
    ;;

  classify)
    validate_digest "$CLASSIFY_DIGEST"
    [[ -n "$REPO_URI" ]] || { echo "pass --service or --repo-uri for --classify mode" >&2; exit 2; }
    CACHE_DIGEST=$(run_gcloud artifacts docker images describe "${REPO_URI}:buildcache" \
      --format 'value(image_summary.digest)' || true)
    echo "digest: $CLASSIFY_DIGEST"
    if [[ "$CLASSIFY_DIGEST" == "$CACHE_DIGEST" ]]; then
      echo "classification: buildcache - BuildKit layer cache (mode=max), overwritten per build, never deployed"
      exit 0
    fi
    docker buildx imagetools inspect "${REPO_URI}@${CLASSIFY_DIGEST}" --raw | jq -r '
      if (.mediaType | test("image.index|manifest.list")) then
        "classification: index - OCI image index (what registry tags and Terraform reference); the unknown/unknown child below is the provenance attestation, not a broken image",
        (.manifests[] |
          "  child " +
          (if (.annotations["vnd.docker.reference.type"] // "") == "attestation-manifest"
           then "attestation"
           else ((.platform.os // "?") + "/" + (.platform.architecture // "?")) end)
          + ": " + .digest)
      elif ([.layers[]? | select(.mediaType | test("in-toto"))] | length) > 0 then
        "classification: attestation - BuildKit provenance ("
        + ([.layers[]? | .annotations["in-toto.io/predicate-type"] // empty] | first // "in-toto")
        + "), platform unknown/unknown, never deployed"
      else
        "classification: platform-image - runnable image manifest (what Cloud Run revisions record)"
      end'
    ;;

  service)
    [[ -n "$SERVICE" ]] || { echo "--service required" >&2; exit 2; }
    DEPLOYED=$(service_image "$SERVICE")
    REPO_URI="${REPO_URI:-${DEPLOYED%@*}}"
    INDEX_DIGEST="${DEPLOYED#*@}"
    echo "service: $SERVICE"
    echo "repo_uri: $REPO_URI"
    echo "deployed_index: $INDEX_DIGEST"

    LATEST=$(run_gcloud run services describe "$SERVICE" --region "$REGION" \
      --format 'value(status.latestReadyRevisionName)')
    PLATFORM=$(revision_platform_digest "$LATEST" | sed 's/.*@//')
    echo "latest_ready_revision: $LATEST"
    echo "revision_platform: $PLATFORM"

    AMD64=$(docker buildx imagetools inspect "${REPO_URI}@${INDEX_DIGEST}" --raw | jq -r "$JQ_AMD64")
    echo "index_amd64_child: $AMD64"

    if [[ "$AMD64" == "$PLATFORM" ]]; then
      echo "verdict: VERIFIED - revision runs the image the deployed index describes"
    else
      echo "verdict: MISMATCH - revision digest not found in deployed index (investigate)"
      exit 1
    fi
    ;;
esac
