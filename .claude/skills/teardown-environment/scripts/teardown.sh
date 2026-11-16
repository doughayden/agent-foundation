#!/usr/bin/env bash
# Tear down one environment's terraform/main resources, one evidence-printing step at a time.
# Procedure and rationale: docs/references/environment-teardown.md
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: teardown.sh <command> --env ENV [--workdir DIR] [--apply]

Commands (run in order; each prints a VERDICT line):
  prepare     Worktree from origin/main, var file from the GitHub environment, init, drift plan
  unprotect   Temporary edits + targeted plan; with --apply, applies that plan
  destroy     Destroy plan; with --apply, runs it and classifies the result
  wait-subnet Poll until Cloud Run releases its serverless addresses (max --timeout-min, default 150)
  verify      Confirm the state is empty and the main resources are gone
  cleanup     Remove the worktree (discards the temporary edits)

--workdir defaults to ${TMPDIR:-/tmp}/teardown-ENV. Nothing outside it and the
environment's project changes; only --apply changes Google Cloud or Terraform state.
EOF
}

die() { echo "ERROR: $*" >&2; exit 1; }

CMD="${1:-}"; shift || true
ENV="" WORKDIR="" APPLY=0 TIMEOUT_MIN=150
while [ $# -gt 0 ]; do
  case "$1" in
    --env) ENV="$2"; shift 2 ;;
    --workdir) WORKDIR="$2"; shift 2 ;;
    --apply) APPLY=1; shift ;;
    --timeout-min) TIMEOUT_MIN="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done
[ -n "$CMD" ] && [ -n "$ENV" ] || { usage; exit 2; }

WORKDIR="${WORKDIR:-${TMPDIR:-/tmp}/teardown-${ENV}}"
WORKTREE="$WORKDIR/worktree"
TF_DIR="$WORKTREE/terraform/main"
VAR_FILE="$WORKDIR/${ENV}.tfvars"
PLACEHOLDER="teardown-placeholder"
EDIT_TARGETS="google_sql_database_instance.sessions google_storage_bucket.artifact_service google_vertex_ai_reasoning_engine.session_and_memory"

tf() { terraform -chdir="$TF_DIR" "$@"; }
project() { sed -n 's/^project *= *"\(.*\)"$/\1/p' "$VAR_FILE"; }
region() { sed -n 's/^region *= *"\(.*\)"$/\1/p' "$VAR_FILE"; }
require_prepared() { [ -f "$VAR_FILE" ] && [ -d "$TF_DIR/.terraform" ] || die "run prepare first"; }

# Summarize a saved plan: one line per non-no-op change, then the counts
summarize_plan() {
  tf show -json "$1" | jq -r '
    [.resource_changes[] | select(.change.actions != ["no-op"] and .change.actions != ["read"])] as $c
    | ($c[] | "  \(.change.actions | join("+")) \(.address)"),
      "  totals: " + ([$c[] | .change.actions | join("+")] | group_by(.) | map("\(.[0])=\(length)") | join(" "))'
}

cmd_prepare() {
  mkdir -p "$WORKDIR"
  gcloud auth application-default print-access-token >/dev/null 2>&1 \
    || die "Application Default Credentials missing or expired: gcloud auth application-default login"

  local running
  running=$(gh run list --workflow ci-cd.yml --status in_progress --json headBranch --jq 'length')
  echo "ci-cd.yml runs in progress: $running"

  local vars
  vars=$(gh variable list --env "$ENV" --json name,value) || die "cannot read GitHub environment $ENV"
  # Same GitHub variable → Terraform variable mapping as .github/workflows/terraform-plan-apply.yml
  echo "$vars" | jq -r --arg env "$ENV" '
    (map({(.name): .value}) | add) as $v
    | [["environment", $env],
       ["project", $v.GOOGLE_CLOUD_PROJECT], ["region", $v.REGION], ["zone", $v.ZONE],
       ["google_cloud_location", $v.GOOGLE_CLOUD_LOCATION], ["agent_name", $v.IMAGE_NAME],
       ["terraform_state_bucket", $v.TERRAFORM_STATE_BUCKET],
       ["workload_identity_pool_principal_identifier", $v.WORKLOAD_IDENTITY_POOL_PRINCIPAL_IDENTIFIER]]
    | .[] | select(.[1] != null and .[1] != "") | "\(.[0]) = \"\(.[1])\""' > "$VAR_FILE"
  echo "var file $VAR_FILE:"; sed 's/^/  /' "$VAR_FILE"
  local bucket; bucket=$(sed -n 's/^terraform_state_bucket *= *"\(.*\)"$/\1/p' "$VAR_FILE")
  [ -n "$bucket" ] && [ -n "$(project)" ] || die "GitHub environment $ENV lacks TERRAFORM_STATE_BUCKET or GOOGLE_CLOUD_PROJECT"

  if [ ! -d "$WORKTREE" ]; then
    git fetch -q origin main
    git worktree add -q --detach "$WORKTREE" origin/main
  fi
  echo "worktree $WORKTREE at $(git -C "$WORKTREE" rev-parse --short HEAD)"
  [ ! -f "$TF_DIR/terraform.tfvars" ] || die "$TF_DIR/terraform.tfvars exists and would fill unset variables"

  tf init -input=false -no-color -reconfigure -backend-config="bucket=$bucket" >/dev/null
  echo "state resources: $(tf state list | wc -l | tr -d ' ')"
  # The image falls back to the deployed one; once Cloud Run is gone that fallback is empty
  local image_var=()
  tf state list | grep -q '^google_cloud_run_v2_service\.app' || image_var=(-var "docker_image=$PLACEHOLDER")
  tf plan -input=false -no-color -lock=false -var-file="$VAR_FILE" ${image_var[@]+"${image_var[@]}"} -out="$WORKDIR/drift.tfplan" >/dev/null
  echo "drift plan:"
  summarize_plan "$WORKDIR/drift.tfplan"
  local adds others
  adds=$(tf show -json "$WORKDIR/drift.tfplan" | jq '[.resource_changes[] | select(.change.actions | index("create"))] | length')
  others=$(tf show -json "$WORKDIR/drift.tfplan" | jq '[.resource_changes[] | select((.change.actions | index("delete")) or .change.actions == ["update"])] | length')
  if [ "$adds" -gt 0 ]; then echo "VERDICT: PARTIAL ($adds to create: an earlier destroy already ran; skip unprotect if its targets are gone)"
  elif [ "$others" -gt 0 ]; then echo "VERDICT: DRIFT ($others unexpected changes: stop and compare the var file with the deployed config)"
  else echo "VERDICT: NO_DRIFT"; fi
}

cmd_unprotect() {
  require_prepared
  local db="$TF_DIR/database.tf" main="$TF_DIR/main.tf"
  perl -0pi -e 's/(resource "google_sql_database_instance" "sessions" \{.*?\n\s*deletion_protection\s*=\s*)[^\n]+/${1}false/s' "$db"
  grep -q 'force_destroy *= *true' "$main" \
    || perl -0pi -e 's/(resource "google_storage_bucket" "artifact_service" \{\n)/${1}  force_destroy = true\n/' "$main"
  grep -q 'deletion_policy *= *"FORCE"' "$main" \
    || perl -0pi -e 's/(resource "google_vertex_ai_reasoning_engine" "session_and_memory" \{\n)/${1}  deletion_policy = "FORCE"\n/' "$main"
  tf fmt >/dev/null
  echo "temporary edits:"; git -C "$WORKTREE" diff -U0 -- terraform/main | grep '^[+-] ' | sed 's/^/  /'

  local targets=() t
  for t in $EDIT_TARGETS; do
    tf state list | grep -qx "$t" && targets+=("-target=$t")
  done
  [ ${#targets[@]} -gt 0 ] || { echo "VERDICT: NOTHING_TO_UNPROTECT (no edit target left in state)"; return; }
  tf plan -input=false -no-color -var-file="$VAR_FILE" -var "docker_image=$PLACEHOLDER" "${targets[@]}" -out="$WORKDIR/unprotect.tfplan" >/dev/null
  echo "targeted plan:"; summarize_plan "$WORKDIR/unprotect.tfplan"
  # Only Terraform-side attributes may change, and only in place
  local bad
  bad=$(tf show -json "$WORKDIR/unprotect.tfplan" | jq -r '
    .resource_changes[] | select(.change.actions != ["no-op"] and .change.actions != ["read"])
    | . as $r | ($r.change.before // {}) as $b | ($r.change.after // {}) as $a
    | ([$a | keys[] | select($b[.] != $a[.])] - ["deletion_protection", "force_destroy", "deletion_policy"]) as $extra
    | select($r.change.actions != ["update"] or ($extra | length) > 0)
    | "\($r.address) \($r.change.actions | join("+")) \($extra | join(","))"')
  # shellcheck disable=SC2001  # sed prefixes every line of a multi-line value
  if [ -n "$bad" ]; then echo "$bad" | sed 's/^/  unexpected: /'; echo "VERDICT: UNEXPECTED_CHANGES (do not apply)"; return 1; fi
  if [ "$APPLY" -eq 1 ]; then
    tf apply -input=false -no-color "$WORKDIR/unprotect.tfplan" | grep -E 'Apply complete|Error'
    echo "VERDICT: UNPROTECTED"
  else
    echo "VERDICT: READY_TO_UNPROTECT (re-run with --apply after the user approves)"
  fi
}

cmd_destroy() {
  require_prepared
  tf plan -destroy -input=false -no-color -var-file="$VAR_FILE" -var "docker_image=$PLACEHOLDER" -out="$WORKDIR/destroy.tfplan" >/dev/null
  echo "destroy plan:"; summarize_plan "$WORKDIR/destroy.tfplan"
  if [ "$APPLY" -ne 1 ]; then
    echo "VERDICT: READY_TO_DESTROY (re-run with --apply after the user approves)"; return
  fi
  local log rc=0
  log="$WORKDIR/destroy-$(date -u +%Y%m%dT%H%M%SZ).log"
  echo "started $(date -u +%FT%TZ), log $log"
  tf apply -input=false -no-color "$WORKDIR/destroy.tfplan" > "$log" 2>&1 || rc=$?
  echo "finished $(date -u +%FT%TZ), exit $rc, destroyed $(grep -c 'Destruction complete' "$log" || true)"
  echo "remaining in state:"; tf state list | sed 's/^/  /'
  if [ "$rc" -eq 0 ]; then echo "VERDICT: DESTROYED"; return; fi
  grep '^Error' "$log" | sed 's/^/  /'
  if [ "$(grep -c '^Error' "$log" || true)" -eq "$(grep -c '^Error.*serverless-ipv4' "$log" || true)" ]; then
    echo "VERDICT: SUBNET_HOLD (Cloud Run still holds the subnet: run wait-subnet, then destroy --apply again)"
  else
    echo "VERDICT: FAILED (an error other than the subnet hold: check the blocker table in the doc)"
    return 1
  fi
}

cmd_wait_subnet() {
  require_prepared
  local start; start=$(date +%s)
  echo "waiting from $(date -u +%FT%TZ) for serverless-ipv4 addresses in $(project) to be released"
  while [ -n "$(gcloud compute addresses list --project "$(project)" --filter="region:$(region) AND name~^serverless-ipv4" --format='value(name)')" ]; do
    [ $(( $(date +%s) - start )) -lt $(( TIMEOUT_MIN * 60 )) ] || { echo "VERDICT: STILL_HELD after $TIMEOUT_MIN minutes"; return 1; }
    sleep 300
  done
  echo "VERDICT: RELEASED at $(date -u +%FT%TZ) after $(( ($(date +%s) - start) / 60 )) minutes"
}

cmd_verify() {
  require_prepared
  local p n left=0 failed=0; p=$(project)
  n=$(tf state list | wc -l | tr -d ' '); echo "state resources: $n"; [ "$n" -eq 0 ] || left=1
  # A lookup that fails must not read as "none": report it and withhold TORN_DOWN
  check() {
    local what="$1" pattern="$2" out; shift 2
    if ! out=$("$@" 2>&1); then
      echo "$what: LOOKUP FAILED: $(echo "$out" | head -1)"; failed=1; return
    fi
    # A pattern of !NAME drops lines equal to NAME; any other pattern keeps matching lines
    if [[ "$pattern" == !* ]]; then out=$(echo "$out" | grep -vx "${pattern#!}" || true)
    else out=$(echo "$out" | grep -E "$pattern" || true); fi
    echo "$what: ${out:-none}"; [ -z "$out" ] || left=1
  }
  check "cloud sql instances" '.' gcloud sql instances list --project "$p" --format='value(name)'
  check "cloud run services" '.' gcloud run services list --project "$p" --format='value(metadata.name)'
  check "global addresses" '.' gcloud compute addresses list --global --project "$p" --format='value(name)'
  check "artifact buckets" 'artifact-service' gcloud storage buckets list --project "$p" --format='value(name)'
  check "non-default networks" '!default' gcloud compute networks list --project "$p" --format='value(name)'
  if [ "$failed" -eq 1 ]; then echo "VERDICT: UNVERIFIED (a lookup failed: fix access and re-run verify)"; return 1; fi
  if [ "$left" -eq 0 ]; then echo "VERDICT: TORN_DOWN"; else echo "VERDICT: RESOURCES_REMAIN"; return 1; fi
}

cmd_cleanup() {
  [ -d "$WORKTREE" ] && git worktree remove --force "$WORKTREE"
  echo "VERDICT: CLEANED (var file and logs stay in $WORKDIR)"
}

case "$CMD" in
  prepare) cmd_prepare ;;
  unprotect) cmd_unprotect ;;
  destroy) cmd_destroy ;;
  wait-subnet) cmd_wait_subnet ;;
  verify) cmd_verify ;;
  cleanup) cmd_cleanup ;;
  *) usage; exit 2 ;;
esac
