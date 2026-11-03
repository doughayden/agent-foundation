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
EVAL_DATA_DIR = REPO_ROOT / "tests" / "eval" / "data"
PYTHON_VERSION_FILE = REPO_ROOT / ".python-version"
TERRAFORM_VERSION_FILE = REPO_ROOT / ".terraform-version"
PYPROJECT = REPO_ROOT / "pyproject.toml"
DOCKERFILE = REPO_ROOT / "Dockerfile"
PRE_COMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

DOCKER_FROM = re.compile(r"^FROM\s.*$", re.MULTILINE)
DOCKER_PYTHON_BASE = re.compile(r"\bpython:(?P<version>\d+\.\d+)(?:\.\d+)?(?![\d.])")
PYTHON_VERSION_FORMAT = re.compile(r"\d+\.\d+")
TERRAFORM_VERSION_FORMAT = re.compile(r"\d+\.\d+\.\d+")
UV_VERSION_FORMAT = re.compile(r"(?P<major>\d+)\.(?P<minor>\d+)\.\d+")
DOCKER_UV_IMAGE = re.compile(r"\bghcr\.io/astral-sh/uv:(?P<version>[^\s/]+)")
UV_PRE_COMMIT_REPO = "https://github.com/astral-sh/uv-pre-commit"
TERRAFORM_VERSION_READ = re.compile(r"\bcat \.terraform-version\b")
STEP_OUTPUT_REF = re.compile(r"\$\{\{\s*steps\.(?P<id>[\w-]+)\.outputs\.[\w-]+\s*\}\}")
# Each of these would override .python-version in a workflow
WORKFLOW_PYTHON_OVERRIDES = re.compile(
    r"uv python install[ \t]+[^\s#]|\bpython-version:|\bUV_PYTHON\b|--python(?=[\s=]|$)"
)

# The eval pipeline's scoring model, accepted in one place. Change it here and in
# every eval config together; the agent's ROOT_AGENT_MODEL is a separate choice.
JUDGE_MODEL = "gemini-3.5-flash"


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


class TestUvVersionPins:
    """Exact uv pins agree, and ``required-version`` is their minor-series range."""

    def _exact_pins(self) -> dict[str, str]:
        pins = {
            f"Dockerfile uv image #{index}": match.group("version")
            for index, match in enumerate(
                DOCKER_UV_IMAGE.finditer(DOCKERFILE.read_text()), 1
            )
        }
        assert pins, "no ghcr.io/astral-sh/uv image in Dockerfile"

        hooks = yaml.safe_load(PRE_COMMIT_CONFIG.read_text())["repos"]
        revs = [repo["rev"] for repo in hooks if repo["repo"] == UV_PRE_COMMIT_REPO]
        assert revs, f"no {UV_PRE_COMMIT_REPO} repo in .pre-commit-config.yaml"
        pins |= {f"uv-pre-commit rev #{i}": rev for i, rev in enumerate(revs, 1)}

        setups = {
            f"{workflow.name} {job_id} step {index}": str(
                (step.get("with") or {}).get("version", "<unpinned>")
            )
            for workflow in sorted(WORKFLOWS_DIR.glob("*.y*ml"))
            for job_id, job in yaml.safe_load(workflow.read_text())["jobs"].items()
            for index, step in enumerate(job.get("steps", []), 1)
            if step.get("uses", "").startswith("astral-sh/setup-uv@")
        }
        assert setups, f"no astral-sh/setup-uv step under {WORKFLOWS_DIR}"
        return pins | setups

    def test_exact_uv_pins_agree(self):
        pins = self._exact_pins()
        values = set(pins.values())

        assert len(values) == 1, (
            f"uv pins disagree: {pins}. Set the Dockerfile image, the uv-pre-commit "
            "rev and every setup-uv version input to one exact version"
        )
        assert UV_VERSION_FORMAT.fullmatch(values.pop()), (
            f"uv pins must be exact versions (X.Y.Z): {pins}"
        )

    def test_required_version_is_the_pinned_minor_series(self):
        pinned = next(iter(self._exact_pins().values()))
        match = UV_VERSION_FORMAT.fullmatch(pinned)
        assert match, f"uv pin {pinned!r} is not an exact version (X.Y.Z)"
        major, minor = match.group("major"), int(match.group("minor"))
        expected = f">={major}.{minor},<{major}.{minor + 1}"

        required = tomllib.loads(PYPROJECT.read_text())["tool"]["uv"].get(
            "required-version"
        )
        assert required == expected, (
            f"[tool.uv] required-version is {required!r}, expected {expected!r}: "
            f"the range must be the minor series of the exact pin {pinned}. An "
            "exact == pin blocks every uv command for anyone whose uv moved"
        )


class TestTerraformVersionPin:
    """Every Terraform install in CI reads ``.terraform-version``."""

    def test_terraform_version_file_pins_an_exact_version(self):
        pinned = TERRAFORM_VERSION_FILE.read_text().strip()
        assert TERRAFORM_VERSION_FORMAT.fullmatch(pinned), (
            f".terraform-version holds {pinned!r}: pin an exact version (X.Y.Z)"
        )

    def test_setup_terraform_steps_read_terraform_version_file(self):
        setups = [
            (workflow.name, steps, step)
            for workflow in sorted(WORKFLOWS_DIR.glob("*.y*ml"))
            for job in yaml.safe_load(workflow.read_text())["jobs"].values()
            if (steps := job.get("steps"))
            for step in steps
            if step.get("uses", "").startswith("hashicorp/setup-terraform@")
        ]
        assert setups, f"no hashicorp/setup-terraform step under {WORKFLOWS_DIR}"

        drifted = []
        for name, steps, step in setups:
            version = str(step.get("with", {}).get("terraform_version", ""))
            ref = STEP_OUTPUT_REF.fullmatch(version)
            earlier = steps[: steps.index(step)]
            reads = [
                TERRAFORM_VERSION_READ.search(s.get("run", ""))
                for s in earlier
                if ref and s.get("id") == ref.group("id")
            ]
            if not any(reads):
                drifted.append(f"{name}: {step.get('name', step['uses'])}")
        assert not drifted, (
            f"setup-terraform steps not reading .terraform-version: {drifted}. "
            "Pass terraform_version from an earlier step that reads the file"
        )
