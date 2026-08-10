"""Parity checks for tool versions pinned in more than one place.

A tool pinned in two files drifts silently: nothing connects the pins, and
``pre-commit autoupdate`` moves one of them on its own. Each check here reads
both pins from their real files and fails the unit lane when they disagree.

Add a case whenever a new pin gains a second home.
"""

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PRE_COMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

ACTIONLINT_REPO = "https://github.com/rhysd/actionlint"
ACTIONLINT_IMAGE = re.compile(r"docker://rhysd/actionlint:(?P<version>[\w.\-]+)")


def _hook_rev(repo_url: str) -> str:
    """Return the pinned ``rev`` for a pre-commit repo, without a leading ``v``."""
    config = yaml.safe_load(PRE_COMMIT_CONFIG.read_text())
    revs = [repo["rev"] for repo in config["repos"] if repo.get("repo") == repo_url]
    assert revs, f"no pre-commit repo entry for {repo_url}"
    return revs[0].lstrip("v")


class TestActionlintVersionParity:
    """The pre-commit hook and the CI gate run the same actionlint."""

    def test_hook_and_ci_image_pin_the_same_version(self):
        match = ACTIONLINT_IMAGE.search(CI_WORKFLOW.read_text())
        assert match, "no docker://rhysd/actionlint image reference in ci.yml"

        assert _hook_rev(ACTIONLINT_REPO) == match.group("version").lstrip("v"), (
            "actionlint version drift: bump the hook rev in .pre-commit-config.yaml "
            "and the image tag in ci.yml together"
        )
