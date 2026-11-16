"""Tests for ``.github/workflows/scripts/promotion-summary.sh``.

The script copies the promotion block from ``docs/releasing.md`` (the one fenced block
that pushes the promotion tag) and writes one merge-run summary. These tests run the
real script: ``--extract`` against the real doc and crafted docs, and the report
against a fake ``gh`` that pipes GitHub-shaped JSON through the script's own ``--jq``
filters. A doc edit that breaks the block, or a script change that drops a message,
fails the unit lane instead of a release's merge run.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "workflows" / "scripts" / "promotion-summary.sh"
RELEASING_DOC = REPO_ROOT / "docs" / "releasing.md"
SHA = "f16ea7f571f4a962f32a3bde63c41692196c8704"
OTHER_SHA = "0a8180a0000000000000000000000000000000ff"
MANIFEST_FILE = ".release-please-manifest.json"
DOCS_URL = "https://github.example/owner/repo/blob/sha/docs/releasing.md#promote"
PUSH_LINE = 'git push origin "prod-${VERSION}"'
LOOKUP_LINE = (
    "VERSION=$(git describe --tags --abbrev=0 --match 'v[0-9]*' origin/main) &&"
)
BLOCK_DOC = f"""2. Paste this:
   ```bash
   {{
     {LOOKUP_LINE}
     {PUSH_LINE}
   }}
   ```
"""


def _extract(doc: Path) -> str:
    result = subprocess.run(  # noqa: S603 - runs the repo's own script
        ["/bin/bash", str(SCRIPT), "--extract", str(doc)],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _run_report(
    bin_dir: Path, tmp_path: Path, doc: Path = RELEASING_DOC
) -> tuple[str, str]:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({".": "1.2.3"}))
    summary = tmp_path / "summary.md"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "GH_TOKEN": "test-token",
        "REPO": "owner/repo",
        "SHA": SHA,
        "REPO_URL": "https://github.example/owner/repo",
        "DOCS_URL": DOCS_URL,
        "DOC": str(doc),
        "MANIFEST": str(manifest),
        "GITHUB_STEP_SUMMARY": str(summary),
    }
    result = subprocess.run(  # noqa: S603 - runs the repo's own script
        ["/bin/bash", str(SCRIPT)], env=env, check=True, capture_output=True, text=True
    )
    return summary.read_text(), result.stdout


@pytest.fixture
def releasing_block() -> str:
    return _extract(RELEASING_DOC)


class TestPromotionBlockExtraction:
    def test_releasing_doc_block_is_the_guarded_tag_push(self, releasing_block):
        assert "```" not in releasing_block
        assert PUSH_LINE in releasing_block
        assert "read -r REPLY </dev/tty" in releasing_block
        assert LOOKUP_LINE in releasing_block

    def test_releasing_doc_block_parses_in_bash(self, releasing_block, tmp_path):
        block = tmp_path / "block.sh"
        block.write_text(releasing_block)

        subprocess.run(["/bin/bash", "-n", str(block)], check=True)  # noqa: S603

    @pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh not installed")
    def test_releasing_doc_block_parses_in_zsh(self, releasing_block, tmp_path):
        block = tmp_path / "block.sh"
        block.write_text(releasing_block)
        zsh = shutil.which("zsh")
        assert zsh is not None

        subprocess.run([zsh, "-n", str(block)], check=True)  # noqa: S603

    @pytest.mark.parametrize(
        "doc_text",
        [
            pytest.param("No code blocks here.\n", id="no-block"),
            pytest.param(BLOCK_DOC + BLOCK_DOC, id="two-matching-blocks"),
            pytest.param("```bash\n" + PUSH_LINE + "\n", id="unclosed-fence"),
            pytest.param("```bash\necho unrelated\n```\n", id="no-push-line"),
        ],
    )
    def test_extract_prints_nothing_without_exactly_one_closed_block(
        self, doc_text, tmp_path
    ):
        doc = tmp_path / "releasing.md"
        doc.write_text(doc_text)

        assert _extract(doc) == ""

    def test_extract_strips_the_list_item_indent(self, tmp_path):
        doc = tmp_path / "releasing.md"
        doc.write_text(BLOCK_DOC)

        expected = ["{", f"  {LOOKUP_LINE}", f"  {PUSH_LINE}", "}"]
        assert _extract(doc).splitlines() == expected


class TestPromotionSummaryReport:
    def test_non_release_commit_reports_nothing_to_promote(
        self, create_mock_gh, tmp_path
    ):
        gh = create_mock_gh(sha=SHA, files=["src/app.py"], tag_sha=None)

        summary, _ = _run_report(gh, tmp_path)

        assert "## Promotion Summary" in summary
        assert "`f16ea7f` is not a release commit: nothing to promote." in summary

    @pytest.mark.parametrize(
        "tag_sha",
        [pytest.param(None, id="no-tag"), pytest.param(OTHER_SHA, id="tag-elsewhere")],
    )
    def test_untagged_release_warns_without_a_link(
        self, create_mock_gh, tag_sha, tmp_path
    ):
        gh = create_mock_gh(sha=SHA, files=[MANIFEST_FILE], tag_sha=tag_sha)

        summary, stdout = _run_report(gh, tmp_path)

        assert "## ⚠️ Release not tagged yet" in summary
        assert "no `v1.2.3` tag marks it yet" in summary
        assert "by hand when releases are cut without the App" in summary
        assert "`docs/releasing.md`, section Promote to Production" in summary
        assert "http" not in summary
        assert "::warning::v1.2.3 does not mark f16ea7f yet" in stdout

    def test_tagged_release_prints_the_block_pinned_to_its_version(
        self, create_mock_gh, releasing_block, tmp_path
    ):
        gh = create_mock_gh(sha=SHA, files=[MANIFEST_FILE], tag_sha=SHA)

        summary, _ = _run_report(gh, tmp_path)

        pinned = releasing_block.replace(LOOKUP_LINE, "VERSION=v1.2.3 &&")
        assert pinned != releasing_block
        assert "## 🚀 Ready to promote v1.2.3" in summary
        assert "https://github.example/owner/repo/releases/tag/v1.2.3" in summary
        assert DOCS_URL in summary
        assert f"```bash\n{pinned}```" in summary

    def test_tagged_release_without_a_block_warns_and_links(
        self, create_mock_gh, tmp_path
    ):
        gh = create_mock_gh(sha=SHA, files=[MANIFEST_FILE], tag_sha=SHA)
        doc = tmp_path / "releasing.md"
        doc.write_text("# Releasing\n\nNo block here.\n")

        summary, stdout = _run_report(gh, tmp_path, doc)

        assert "## 🚀 Ready to promote v1.2.3" in summary
        assert "```" not in summary
        assert DOCS_URL in summary
        assert "::warning::No promotion block" in stdout

    @pytest.mark.parametrize(
        ("fail", "read"),
        [
            pytest.param("files", "commit files", id="files-read"),
            pytest.param("tag", "tag v1.2.3", id="tag-read"),
        ],
    )
    def test_api_failure_reports_unknown_status_and_exits_zero(
        self, create_mock_gh, fail, read, tmp_path
    ):
        gh = create_mock_gh(sha=SHA, files=[MANIFEST_FILE], tag_sha=SHA, fail=fail)

        summary, stdout = _run_report(gh, tmp_path)

        assert "## ⚠️ Promotion status unknown" in summary
        assert f"The GitHub API read failed ({read})" in summary
        assert "`docs/releasing.md`, section Promote to Production" in summary
        assert f"::warning::GitHub API read failed: {read}" in stdout
