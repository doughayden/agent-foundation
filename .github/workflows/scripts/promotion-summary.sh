#!/usr/bin/env bash
# Writes the merge run's promotion summary. Always writes exactly one message and exits 0,
# so an informational job never fails a green deploy run:
#   - tagged release: the promotion block from docs/releasing.md, pinned to the version
#   - release commit without its tag yet: a warning naming the docs section
#   - any other commit: nothing to promote
#   - GitHub API error: a warning naming the docs section
# The block's only source is docs/releasing.md: the one fenced block that pushes the
# promotion tag (git push origin "prod-${VERSION}").
#
# Usage:
#   promotion-summary.sh                  # report (CI); reads the environment below
#   promotion-summary.sh --extract DOC    # print the promotion block from DOC
#
# Environment (report mode): GH_TOKEN, REPO, SHA, REPO_URL, DOCS_URL, DOC, MANIFEST,
# GITHUB_STEP_SUMMARY.
set -euo pipefail

DOCS_SECTION="\`docs/releasing.md\`, section Promote to Production"

# Prints the one fenced block that pushes the promotion tag, with the list-item indent
# removed; prints nothing unless exactly one closed fenced block does
extract_block() {
  awk '
    /^[[:space:]]*```/ {
      if (inside) { inside = 0; if (index(buffer, PUSH)) { matches++; found = buffer } }
      else { inside = 1; buffer = "" }
      next
    }
    inside { sub(/^   /, ""); buffer = buffer $0 "\n" }
    END { if (matches == 1 && !inside) printf "%s", found }
  ' PUSH='git push origin "prod-${VERSION}"' "$1"
}

summary() {
  printf '%s\n' "$@" >> "$GITHUB_STEP_SUMMARY"
}

api_error() {
  echo "::warning::GitHub API read failed: $1"
  summary "## ⚠️ Promotion status unknown" \
    "The GitHub API read failed ($1), so this run could not check \`${short_sha}\`." \
    "" \
    "If this is a release commit, promote it with the guarded block in ${DOCS_SECTION}."
  exit 0
}

if [ "${1:-}" = "--extract" ]; then
  extract_block "$2"
  exit 0
fi

short_sha="${SHA:0:7}"

# Every release-please merge commit bumps the manifest
release=$(gh api "repos/${REPO}/commits/${SHA}" --jq 'any(.files[]; .filename == ".release-please-manifest.json")') \
  || api_error "commit files"
if [ "${release}" != "true" ]; then
  summary "## Promotion Summary" "\`${short_sha}\` is not a release commit: nothing to promote."
  exit 0
fi

version="v$(jq -r '."."' "$MANIFEST")"
if ! tag_output=$(gh api "repos/${REPO}/commits/${version}" --jq '.sha' 2>&1); then
  case "${tag_output}" in
    *"HTTP 404"* | *"HTTP 422"*) tag_sha="" ;;
    *) api_error "tag ${version}" ;;
  esac
else
  tag_sha="${tag_output}"
fi

if [ "${tag_sha}" != "${SHA}" ]; then
  echo "::warning::${version} does not mark ${short_sha} yet"
  summary "## ⚠️ Release not tagged yet" \
    "Stage and the judge eval passed on release commit \`${short_sha}\`, but no \`${version}\` tag marks it yet." \
    "" \
    "Once the tag exists (from this commit's Release workflow run, or by hand when releases are cut without the App), promote it with the guarded block in ${DOCS_SECTION}."
  exit 0
fi

block=$(extract_block "$DOC")
summary "## 🚀 Ready to promote ${version}" \
  "Stage and the judge eval passed on \`${short_sha}\` ([${version}](${REPO_URL}/releases/tag/${version}))." \
  ""
pinned=$(printf '%s\n' "${block}" | sed "s|^\([[:space:]]*\)VERSION=\$(git describe .*) &&\$|\1VERSION=${version} \&\&|")
if [ -n "${block}" ] && [ "${pinned}" != "${block}" ]; then
  summary "Paste this block whole in a clone of the repo. It is pinned to ${version}, prints the commit, and waits for \`y\` before it pushes \`prod-${version}\` ([Releasing: Promote to Production](${DOCS_URL})):" \
    "" \
    '```bash' \
    "${pinned}" \
    '```'
else
  echo "::warning::No promotion block with a VERSION lookup line in ${DOC}"
  summary "Promote it with the guarded block in [Releasing: Promote to Production](${DOCS_URL})."
fi
