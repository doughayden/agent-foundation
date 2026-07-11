"""Unit tests for the App-aware eval-inference monkey-patch.

Proves, without a live model, that the patch installs and that the eval
``Runner`` is built from the ``App`` (its plugins applied) rather than the bare
``root_agent``. The ``Runner`` is mocked to capture its construction kwargs and
the user simulator yields no message, so the inference loop breaks before any
model call.
"""

from types import SimpleNamespace
from typing import Any

import pytest
from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.evaluation import evaluation_generator as eg
from google.adk.plugins.logging_plugin import LoggingPlugin

# Importing the package runs its __init__, which applies the patch; that import
# side effect is what test_patch_installed_on_import verifies.
from agent_foundation import _eval_app_aware_patch as patch_mod

# ADK's _generate_inferences_from_root_agent always injects these two internal
# eval plugins into the Runner (the request intercepter that captures app_details
# and the retry-options plugin). The patch merges them alongside app.plugins, so
# the assertions below check the resulting count against this named anchor rather
# than a bare literal — if ADK changes its internal set, both fail at one place.
INTERNAL_PLUGIN_COUNT = 2


@pytest.fixture
def runner_capture(mocker):
    """Patch ``evaluation_generator.Runner`` to record its kwargs.

    Returns the dict that the patched Runner factory fills on construction. The
    returned object is a no-op async context manager so ``async with`` succeeds.
    """
    captured: dict[str, Any] = {}

    def _factory(**kwargs: Any) -> Any:
        captured.clear()
        captured.update(kwargs)
        cm = mocker.MagicMock()
        cm.__aenter__ = mocker.AsyncMock(return_value=cm)
        cm.__aexit__ = mocker.AsyncMock(return_value=None)
        return cm

    mocker.patch.object(eg, "Runner", side_effect=_factory)
    return captured


@pytest.fixture
def no_message_simulator(mocker):
    """A user simulator that ends the conversation before any model call."""
    simulator = mocker.MagicMock()
    simulator.get_next_user_message = mocker.AsyncMock(
        return_value=SimpleNamespace(
            status=eg.UserSimulatorStatus.NO_MESSAGE_GENERATED,
            user_message=None,
        )
    )
    return simulator


async def _run_leaf(root_agent, simulator, app=None):
    """Invoke the patched inference leaf through the class (as ADK does)."""
    return await eg.EvaluationGenerator._generate_inferences_from_root_agent(
        root_agent=root_agent,
        user_simulator=simulator,
        app=app,
    )


class TestPatchInstallation:
    """The apply-trigger installs the App-aware leaf and is idempotent."""

    def test_patch_installed_on_import(self):
        assert getattr(eg.EvaluationGenerator, "_app_aware_eval_patched", False)
        assert (
            eg.EvaluationGenerator._generate_inferences_from_root_agent.__name__
            == "_app_aware_generate_inferences_from_root_agent"
        )

    def test_apply_is_idempotent(self):
        patch_mod.apply_app_aware_eval_patch()
        patch_mod.apply_app_aware_eval_patch()
        assert getattr(eg.EvaluationGenerator, "_app_aware_eval_patched", False)


class TestAppAwareRunner:
    """The eval Runner is built from the App, applying its plugins."""

    async def test_explicit_app_plugins_flow_to_runner(
        self, runner_capture, no_message_simulator
    ):
        sentinel_plugin = LoggingPlugin(name="sentinel")
        app = App(
            name="explicit_app",
            root_agent=LlmAgent(name="app_root", model="gemini-2.5-flash"),
            plugins=[sentinel_plugin],
        )
        override_agent = LlmAgent(name="override", model="gemini-2.5-flash")

        await _run_leaf(override_agent, no_message_simulator, app=app)

        runner_app = runner_capture["app"]
        assert sentinel_plugin in runner_app.plugins
        assert len(runner_app.plugins) == 1 + INTERNAL_PLUGIN_COUNT
        assert runner_app.root_agent is override_agent
        # The caller's App is copied, not mutated.
        assert app.plugins == [sentinel_plugin]

    async def test_self_sources_package_app_when_none(
        self, runner_capture, no_message_simulator, mocker
    ):
        sentinel_plugin = LoggingPlugin(name="self_sourced")
        package_app = App(
            name="package_app",
            root_agent=LlmAgent(name="pkg_root", model="gemini-2.5-flash"),
            plugins=[sentinel_plugin],
        )
        mocker.patch.object(patch_mod, "_resolve_package_app", return_value=package_app)
        override_agent = LlmAgent(name="override", model="gemini-2.5-flash")

        await _run_leaf(override_agent, no_message_simulator, app=None)

        assert sentinel_plugin in runner_capture["app"].plugins

    async def test_bare_agent_path_when_no_app(
        self, runner_capture, no_message_simulator, mocker
    ):
        mocker.patch.object(patch_mod, "_resolve_package_app", return_value=None)
        bare_agent = LlmAgent(name="bare", model="gemini-2.5-flash")

        await _run_leaf(bare_agent, no_message_simulator, app=None)

        assert "app" not in runner_capture
        assert runner_capture["agent"] is bare_agent
        assert len(runner_capture["plugins"]) == INTERNAL_PLUGIN_COUNT

    async def test_success_path_drives_inference_loop(self, runner_capture, mocker):
        """A SUCCESS turn appends events and passes them to the converter.

        Also exercises the caller-supplied session/memory/artifact services,
        the seeded initial session, and the reset hook.
        """
        simulator = mocker.MagicMock()
        simulator.get_next_user_message = mocker.AsyncMock(
            side_effect=[
                SimpleNamespace(
                    status=eg.UserSimulatorStatus.SUCCESS, user_message=None
                ),
                SimpleNamespace(
                    status=eg.UserSimulatorStatus.NO_MESSAGE_GENERATED,
                    user_message=None,
                ),
            ]
        )
        sentinel_event = object()

        async def _one_event(*_args, **_kwargs):
            yield sentinel_event

        mocker.patch.object(
            eg.EvaluationGenerator,
            "_generate_inferences_for_single_user_invocation",
            side_effect=_one_event,
        )
        mocker.patch.object(
            eg.EvaluationGenerator,
            "_get_app_details_by_invocation_id",
            return_value={},
        )
        converted = [object()]
        convert = mocker.patch.object(
            eg.EvaluationGenerator,
            "convert_events_to_eval_invocations",
            return_value=converted,
        )
        reset_func = mocker.MagicMock()

        result = await eg.EvaluationGenerator._generate_inferences_from_root_agent(
            root_agent=LlmAgent(name="override", model="gemini-2.5-flash"),
            user_simulator=simulator,
            reset_func=reset_func,
            initial_session=SimpleNamespace(
                app_name="seeded", user_id="seed_user", state={"k": "v"}
            ),
            session_id="fixed-session",
            session_service=eg.InMemorySessionService(),
            memory_service=eg.InMemoryMemoryService(),
            artifact_service=eg.InMemoryArtifactService(),
            app=App(
                name="seeded_app",
                root_agent=LlmAgent(name="app_root", model="gemini-2.5-flash"),
                plugins=[LoggingPlugin(name="seeded")],
            ),
        )

        reset_func.assert_called_once()
        assert convert.call_args.args[0] == [sentinel_event]
        assert result is converted


class TestResolvePackageApp:
    """Self-source resolves this package's App instance."""

    def test_resolves_the_agent_package_app(self):
        from agent_foundation import agent as agent_module

        assert patch_mod._resolve_package_app() is agent_module.app

    def test_returns_none_when_module_has_no_app(self, mocker):
        mocker.patch.object(
            patch_mod.importlib,
            "import_module",
            return_value=SimpleNamespace(),
        )
        assert patch_mod._resolve_package_app() is None
