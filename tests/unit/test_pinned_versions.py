"""Parity checks for versions pinned in more than one place.

A value pinned in several files drifts silently: nothing connects the pins, and
``pre-commit autoupdate`` moves one of them on its own. Each check here reads
the pins from their real files and fails the unit lane when they disagree.

Add a case whenever a new pin gains a second home.
"""

import json
import re
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PRE_COMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
EVAL_DATA_DIR = REPO_ROOT / "tests" / "eval" / "data"
PYTHON_VERSION_FILE = REPO_ROOT / ".python-version"
PYPROJECT = REPO_ROOT / "pyproject.toml"
DOCKERFILE = REPO_ROOT / "Dockerfile"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

ACTIONLINT_REPO = "https://github.com/rhysd/actionlint"
ACTIONLINT_IMAGE = re.compile(r"docker://rhysd/actionlint:(?P<version>[\w.\-]+)")
DOCKER_FROM = re.compile(r"^FROM\s.*$", re.MULTILINE)
DOCKER_PYTHON_BASE = re.compile(r"\bpython:(?P<version>\d+\.\d+)(?:\.\d+)?(?![\d.])")
PYTHON_VERSION_FORMAT = re.compile(r"\d+\.\d+")
# Each of these would override .python-version in a workflow
WORKFLOW_PYTHON_OVERRIDES = re.compile(
    r"uv python install[ \t]+[^\s#]|\bpython-version:|\bUV_PYTHON\b|--python(?=[\s=]|$)"
)

# The eval pipeline's scoring model, accepted in one place. Change it here and in
# every eval config together; the agent's ROOT_AGENT_MODEL is a separate choice.
JUDGE_MODEL = "gemini-3.5-flash"


def _hook_rev(repo_url: str) -> str:
    """Return the pinned ``rev`` for a pre-commit repo, without a leading ``v``."""
    config = yaml.safe_load(PRE_COMMIT_CONFIG.read_text())
    revs = [repo["rev"] for repo in config["repos"] if repo.get("repo") == repo_url]
    assert revs, f"no pre-commit repo entry for {repo_url}"
    rev = revs[0]
    assert isinstance(rev, str), f"pre-commit rev for {repo_url} is not a string"
    return rev.lstrip("v")


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


class TestPythonVersionParity:
    """Every interpreter pin follows ``.python-version``."""

    def _pinned(self) -> tuple[int, int]:
        pinned = PYTHON_VERSION_FILE.read_text().strip()
        assert PYTHON_VERSION_FORMAT.fullmatch(pinned), (
            f".python-version holds {pinned!r}: pin major.minor only (X.Y)"
        )
        major, minor = pinned.split(".")
        return int(major), int(minor)

    def test_pyproject_pins_follow_python_version_file(self):
        major, minor = self._pinned()
        pyproject = tomllib.loads(PYPROJECT.read_text())

        assert pyproject["project"]["requires-python"] == (
            f">={major}.{minor},<{major}.{minor + 1}"
        ), "requires-python drifted from .python-version"
        assert pyproject["tool"]["ruff"]["target-version"] == f"py{major}{minor}", (
            "ruff target-version drifted from .python-version"
        )
        assert pyproject["tool"]["mypy"]["python_version"] == f"{major}.{minor}", (
            "mypy python_version drifted from .python-version"
        )

    def test_dockerfile_base_images_follow_python_version_file(self):
        major, minor = self._pinned()
        stages = DOCKER_FROM.findall(DOCKERFILE.read_text())
        assert stages, "no FROM stage in Dockerfile"

        drifted = [
            stage
            for stage in stages
            if not (match := DOCKER_PYTHON_BASE.search(stage))
            or match.group("version") != f"{major}.{minor}"
        ]
        assert not drifted, (
            f"Dockerfile stages {drifted} do not use python:{major}.{minor} "
            "from .python-version"
        )

    def test_workflows_take_python_from_python_version_file(self):
        workflows = sorted(WORKFLOWS_DIR.glob("*.y*ml"))
        assert workflows, f"no workflows found under {WORKFLOWS_DIR}"

        overrides = [
            f"{workflow.name}:{lineno}"
            for workflow in workflows
            for lineno, line in enumerate(workflow.read_text().splitlines(), 1)
            if not line.lstrip().startswith("#")
            and WORKFLOW_PYTHON_OVERRIDES.search(line.split(" #", 1)[0])
        ]
        assert not overrides, (
            f"workflow Python version override at {overrides}: drop it so CI "
            "reads .python-version"
        )
