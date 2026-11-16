#!/usr/bin/env bash
# Writes the merge run's promotion summary: the promotion block for a tagged release, a
# not-tagged-yet warning for an untagged release, or "nothing to promote" for any other
# commit. Always prints one message. The block is copied from docs/releasing.md between
# the prod-promotion markers, so the doc stays its only source.
#
# Usage:
#   promotion-summary.sh                  # report (CI); reads the environment below
#   promotion-summary.sh --extract DOC    # print the promotion block from DOC
#
# Environment (report mode): GH_TOKEN, REPO, SHA, REPO_URL, DOCS_URL, DOC,
# GITHUB_STEP_SUMMARY.
set -euo pipefail

extract_block() {
  awk '/<!-- prod-promotion:end -->/ { inside = 0 }
    inside && !/^[[:space:]]*```/ { sub(/^   /, ""); print }
    /<!-- prod-promotion:start -->/ { inside = 1 }' "$1"
}

if [ "${1:-}" = "--extract" ]; then
  extract_block "$2"
  exit 0
fi

short_sha="${SHA:0:7}"

# Every release-please merge commit bumps the manifest
release=$(gh api "repos/${REPO}/commits/${SHA}" --jq 'any(.files[]; .filename == ".release-please-manifest.json")')
if [ "${release}" != "true" ]; then
  {
    echo "## Promotion Summary"
    echo "\`${short_sha}\` is not a release commit: nothing to promote."
  } >> "$GITHUB_STEP_SUMMARY"
  exit 0
fi

version=$(gh api "repos/${REPO}/tags" --paginate --jq ".[] | select(.commit.sha == \"${SHA}\") | .name" | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | head -n 1 || true)
if [ -z "${version}" ]; then
  echo "::warning::No vX.Y.Z tag marks ${short_sha} yet"
  {
    echo "## ⚠️ Release not tagged yet"
    echo "Stage and the judge eval passed on release commit \`${short_sha}\`, but no \`vX.Y.Z\` tag marks it yet."
    echo ""
    echo "Once this commit's Release workflow run finishes, promote it with the guarded block in \`docs/releasing.md\`, section Promote to Production."
  } >> "$GITHUB_STEP_SUMMARY"
  exit 0
fi

block=$(extract_block "$DOC")
{
  echo "## 🚀 Ready to promote ${version}"
  echo "Stage and the judge eval passed on \`${short_sha}\` ([${version}](${REPO_URL}/releases/tag/${version}))."
  echo ""
} >> "$GITHUB_STEP_SUMMARY"
if [ -n "${block}" ]; then
  {
    echo "Paste this block whole in a clone of the repo. It prints the version it found and waits for \`y\` before it pushes the promotion tag ([Releasing: Promote to Production](${DOCS_URL})):"
    echo ""
    echo '```bash'
    echo "${block}"
    echo '```'
  } >> "$GITHUB_STEP_SUMMARY"
else
  echo "::warning::No promotion block between the prod-promotion markers in ${DOC}"
  echo "Promote it with the guarded block in [Releasing: Promote to Production](${DOCS_URL})." >> "$GITHUB_STEP_SUMMARY"
fi
