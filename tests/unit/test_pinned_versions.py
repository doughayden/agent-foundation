"""Parity checks for versions pinned in more than one place.

A value pinned in several files drifts silently: nothing connects the pins, and
``pre-commit autoupdate`` moves one of them on its own. Each check here reads
the pins from their real files and fails the unit lane when they disagree.

Add a case whenever a new pin gains a second home.
"""

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PRE_COMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
EVAL_DATA_DIR = REPO_ROOT / "tests" / "eval" / "data"

ACTIONLINT_REPO = "https://github.com/rhysd/actionlint"
ACTIONLINT_IMAGE = re.compile(r"docker://rhysd/actionlint:(?P<version>[\w.\-]+)")

# The eval pipeline's scoring model, accepted in one place. Change it here and in
# every eval config together; the agent's ROOT_AGENT_MODEL is a separate choice.
JUDGE_MODEL = "gemini-3.5-flash"


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


def _eval_model_pins(node: Any, path: str) -> Iterator[tuple[str, str]]:
    """Yield ``(location, model)`` for every judge and user-simulator model."""
    if isinstance(node, dict):
        for key, value in node.items():
            location = f"{path}.{key}"
            if key == "judge_model" or (
                key == "model" and path.endswith(".user_simulator_config")
            ):
                yield location, value
            else:
                yield from _eval_model_pins(value, location)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from _eval_model_pins(item, f"{path}[{index}]")


class TestJudgeModelPin:
    """Every eval config scores with the accepted judge model."""

    def test_eval_configs_use_the_pinned_judge_model(self):
        pins = [
            pin
            for config in sorted(EVAL_DATA_DIR.glob("*.json"))
            for pin in _eval_model_pins(json.loads(config.read_text()), config.name)
        ]
        assert pins, f"no judge_model entries found under {EVAL_DATA_DIR}"

        drifted = [f"{loc} = {model!r}" for loc, model in pins if model != JUDGE_MODEL]
        assert not drifted, (
            f"judge model drift from JUDGE_MODEL = {JUDGE_MODEL!r}: {drifted}. "
            "Bump JUDGE_MODEL and every eval config entry together"
        )
