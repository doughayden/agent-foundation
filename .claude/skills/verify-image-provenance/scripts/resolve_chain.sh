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
# The repo URI is derived from the service spec when omitted.
set -euo pipefail

PROJECT="" REGION="" SERVICE="" REVISION="" TAG="" FIND_DIGEST="" REPO_URI=""
COMPARE_A="" COMPARE_B="" CLASSIFY_DIGEST=""
MODE="service"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    --verify) MODE="service"; shift ;;
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

# Modes needing a repo URI can derive it from --service instead of --repo-uri
if [[ -z "$REPO_URI" && -n "$SERVICE" && "$MODE" != "service" ]]; then
  REPO_URI=$(gcloud run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" 2>/dev/null \
    --format 'value(spec.template.spec.containers[0].image)' | cut -d'@' -f1)
fi

run_gcloud() { gcloud "$@" --project "$PROJECT" 2>/dev/null; }

revision_platform_digest() {
  run_gcloud run revisions describe "$1" --region "$REGION" \
    --format 'value(spec.containers[0].image)'
}

service_image() {
  run_gcloud run services describe "$1" --region "$REGION" \
    --format 'value(spec.template.spec.containers[0].image)'
}

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
    [[ -n "$REPO_URI" ]] || { echo "--repo-uri required for --tag mode" >&2; exit 2; }
    INDEX=$(run_gcloud artifacts docker images describe "${REPO_URI}:${TAG}" \
      --format 'value(image_summary.digest)')
    echo "tag: $TAG"
    echo "index_digest: $INDEX"
    echo "children:"
    docker buildx imagetools inspect "${REPO_URI}@${INDEX}" --raw \
      | python3 -c '
import json, sys
for m in json.load(sys.stdin).get("manifests", []):
    plat = m.get("platform") or {}
    ref = (m.get("annotations") or {}).get("vnd.docker.reference.type", "")
    kind = "attestation" if ref == "attestation-manifest" else plat.get("os", "?") + "/" + plat.get("architecture", "?")
    print("  " + kind + ": " + m["digest"])'
    echo "note: the artifact shown as platform unknown/unknown in registry UIs is the attestation child above (BuildKit provenance), never the index and never a broken image"
    ;;

  find-commit)
    [[ -n "$REPO_URI" ]] || { echo "--repo-uri required for --find-commit mode" >&2; exit 2; }
    echo "searching tagged indexes for platform digest: $FIND_DIGEST"
    FOUND=""
    while read -r T D; do
      [[ "$T" =~ ^(latest|buildcache|pr-.*)$ ]] && continue
      CHILD=$(docker buildx imagetools inspect "${REPO_URI}@${D}" --raw 2>/dev/null \
        | python3 -c 'import json,sys; print(next((m["digest"] for m in json.load(sys.stdin).get("manifests",[]) if (m.get("platform") or {}).get("architecture")=="amd64"),""))' || true)
      if [[ "$CHILD" == "$FIND_DIGEST" ]]; then
        echo "match: tag=$T index=$D"
        FOUND=1
      fi
    done < <(run_gcloud artifacts docker tags list "$REPO_URI" \
      --format 'value(tag.basename(), version.basename())')
    [[ -n "$FOUND" ]] || { echo "no tagged index contains $FIND_DIGEST"; exit 1; }
    ;;

  classify)
    [[ -n "$REPO_URI" ]] || { echo "--repo-uri required for --classify mode" >&2; exit 2; }
    # buildcache check: compare against the buildcache tag's digest
    CACHE_DIGEST=$(run_gcloud artifacts docker images describe "${REPO_URI}:buildcache" \
      --format 'value(image_summary.digest)' || true)
    if [[ "$CLASSIFY_DIGEST" == "$CACHE_DIGEST" ]]; then
      echo "digest: $CLASSIFY_DIGEST"
      echo "classification: buildcache - BuildKit layer cache (mode=max), overwritten per build, never deployed"
      exit 0
    fi
    RAW=$(docker buildx imagetools inspect "${REPO_URI}@${CLASSIFY_DIGEST}" --raw)
    echo "digest: $CLASSIFY_DIGEST"
    echo "$RAW" | python3 -c '
import json, sys
doc = json.load(sys.stdin)
mt = doc.get("mediaType", "")
if "image.index" in mt or "manifest.list" in mt:
    print("classification: index - OCI image index (what registry tags and Terraform reference); the unknown/unknown child below is the provenance attestation, not a broken image")
    for m in doc.get("manifests", []):
        plat = m.get("platform") or {}
        ref = (m.get("annotations") or {}).get("vnd.docker.reference.type", "")
        kind = "attestation" if ref == "attestation-manifest" else plat.get("os", "?") + "/" + plat.get("architecture", "?")
        print("  child " + kind + ": " + m["digest"])
elif any("in-toto" in (l.get("mediaType") or "") for l in doc.get("layers", [])):
    pt = next(((l.get("annotations") or {}).get("in-toto.io/predicate-type", "") for l in doc.get("layers", []) if l.get("annotations")), "")
    print("classification: attestation - BuildKit provenance (" + (pt or "in-toto") + "), platform unknown/unknown, never deployed")
else:
    print("classification: platform-image - runnable image manifest (what Cloud Run revisions record)")'
    # if it is a platform image or attestation, find its parent index among tagged indexes
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

    AMD64=$(docker buildx imagetools inspect "${REPO_URI}@${INDEX_DIGEST}" --raw \
      | python3 -c 'import json,sys; print(next((m["digest"] for m in json.load(sys.stdin).get("manifests",[]) if (m.get("platform") or {}).get("architecture")=="amd64"),""))')
    echo "index_amd64_child: $AMD64"

    if [[ "$AMD64" == "$PLATFORM" ]]; then
      echo "verdict: VERIFIED - revision runs the image the deployed index describes"
    else
      echo "verdict: MISMATCH - revision digest not found in deployed index (investigate)"
      exit 1
    fi
    ;;
esac
