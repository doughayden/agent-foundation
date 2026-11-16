"""Tests for ``.github/workflows/scripts/promotion-summary.sh``.

The script copies the promotion block from ``docs/releasing.md`` between the
``prod-promotion`` markers and writes one of three merge-run summaries. These tests run
the real script: ``--extract`` against the real doc, and the report against a fake
``gh`` on ``PATH``, so a doc edit that breaks the block, or a script change that drops
a message, fails the unit lane instead of a release's merge run.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "workflows" / "scripts" / "promotion-summary.sh"
RELEASING_DOC = REPO_ROOT / "docs" / "releasing.md"
START_MARKER = "<!-- prod-promotion:start -->"
END_MARKER = "<!-- prod-promotion:end -->"
SHA = "f16ea7f571f4a962f32a3bde63c41692196c8704"
DOCS_URL = "https://github.example/owner/repo/blob/sha/docs/releasing.md#promote"


def _run_report(
    bin_dir: Path, summary: Path, doc: Path
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "GH_TOKEN": "test-token",
        "REPO": "owner/repo",
        "SHA": SHA,
        "REPO_URL": "https://github.example/owner/repo",
        "DOCS_URL": DOCS_URL,
        "DOC": str(doc),
        "GITHUB_STEP_SUMMARY": str(summary),
    }
    return subprocess.run(  # noqa: S603 - runs the repo's own script
        ["/bin/bash", str(SCRIPT)], env=env, check=True, capture_output=True, text=True
    )


@pytest.fixture
def extracted_block() -> str:
    result = subprocess.run(  # noqa: S603 - runs the repo's own script
        ["/bin/bash", str(SCRIPT), "--extract", str(RELEASING_DOC)],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


class TestPromotionBlockExtraction:
    def test_releasing_doc_has_one_marker_pair_in_order(self):
        text = RELEASING_DOC.read_text()

        assert text.count(START_MARKER) == 1
        assert text.count(END_MARKER) == 1
        assert text.index(START_MARKER) < text.index(END_MARKER)

    def test_extracted_block_is_the_guarded_tag_push(self, extracted_block):
        assert "```" not in extracted_block
        assert 'git push origin "prod-${VERSION}"' in extracted_block
        assert "read -r REPLY </dev/tty" in extracted_block

    def test_extracted_block_parses_in_bash(self, extracted_block, tmp_path):
        block = tmp_path / "block.sh"
        block.write_text(extracted_block)

        subprocess.run(["/bin/bash", "-n", str(block)], check=True)  # noqa: S603

    @pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh not installed")
    def test_extracted_block_parses_in_zsh(self, extracted_block, tmp_path):
        block = tmp_path / "block.sh"
        block.write_text(extracted_block)
        zsh = shutil.which("zsh")
        assert zsh is not None

        subprocess.run([zsh, "-n", str(block)], check=True)  # noqa: S603


class TestPromotionSummaryReport:
    def test_non_release_commit_reports_nothing_to_promote(
        self, create_mock_gh, tmp_path
    ):
        summary = tmp_path / "summary.md"

        _run_report(create_mock_gh(release=False, tags=[]), summary, RELEASING_DOC)

        text = summary.read_text()
        assert "## Promotion Summary" in text
        assert "`f16ea7f` is not a release commit: nothing to promote." in text

    def test_untagged_release_warns_without_a_link(self, create_mock_gh, tmp_path):
        summary = tmp_path / "summary.md"

        result = _run_report(
            create_mock_gh(release=True, tags=["prod-v1.2.3", "v1.2"]),
            summary,
            RELEASING_DOC,
        )

        text = summary.read_text()
        assert "## ⚠️ Release not tagged yet" in text
        assert "`docs/releasing.md`, section Promote to Production" in text
        assert "http" not in text
        assert "::warning::No vX.Y.Z tag marks f16ea7f yet" in result.stdout

    def test_tagged_release_prints_the_block_and_links(
        self, create_mock_gh, extracted_block, tmp_path
    ):
        summary = tmp_path / "summary.md"

        _run_report(
            create_mock_gh(release=True, tags=["prod-v1.2.3", "v1.2.3"]),
            summary,
            RELEASING_DOC,
        )

        text = summary.read_text()
        assert "## 🚀 Ready to promote v1.2.3" in text
        assert "https://github.example/owner/repo/releases/tag/v1.2.3" in text
        assert DOCS_URL in text
        assert f"```bash\n{extracted_block}```" in text

    def test_tagged_release_without_markers_warns_and_links(
        self, create_mock_gh, tmp_path
    ):
        summary = tmp_path / "summary.md"
        doc = tmp_path / "releasing.md"
        doc.write_text("# Releasing\n\nNo markers here.\n")

        result = _run_report(
            create_mock_gh(release=True, tags=["v1.2.3"]), summary, doc
        )

        text = summary.read_text()
        assert "## 🚀 Ready to promote v1.2.3" in text
        assert "```" not in text
        assert DOCS_URL in text
        assert "::warning::No promotion block" in result.stdout
