"""Runtime monkey-patch making ADK eval inference App-aware.

# --- Monkey-patch: App-aware eval inference ---
Bug: every stock ADK eval primitive unwraps to the bare ``root_agent`` and drops
the wrapping ``App`` (its ``plugins``, ``context_cache_config``,
``resumability_config``). An eval therefore scores a different agent than adk web
chat and the deployed server run, and the judge metrics that read ``app_details``
(developer instructions + tool declarations) receive empty context. This is
adk-python#5503.

Patch: replace ``EvaluationGenerator._generate_inferences_from_root_agent`` with a
copy that accepts an optional ``App``, self-sources this package's ``App`` when the
caller passes none, and builds the eval ``Runner`` from
``app.model_copy(update={"plugins": list(app.plugins) + internal_eval_plugins,
"root_agent": root_agent})``. The App's plugins are applied and the post-merge
``LlmRequest`` is captured natively, so ``app_details`` is populated in-process.

This leaf is the single non-live inference choke point every eval surface funnels
through: the ``AgentEvaluator`` gate (``uv run pytest tests/eval``), the adk web
eval tab (``dev_server.run_eval``), and the ``adk eval`` CLI all reach it via
``LocalEvalService._perform_inference_single_eval_item``. Patching it once covers
all of them, so no caller needs to thread ``app=`` explicitly. Self-sourcing is
what makes that possible: the web eval tab runs inside an ``@app.post`` nested
closure that cannot be patched as an attribute, and
``AgentEvaluator._get_eval_results_by_eval_id`` receives only the ``BaseAgent``,
not the module name. The bare-``root_agent`` branch is preserved for the case
where no ``App`` is defined.

Upstream: https://github.com/google/adk-python/issues/5503
          https://github.com/google/adk-python/pull/5534 (CLI-only fix, stalled)
TODO: Remove this module and its apply-trigger in ``__init__`` once an App-aware
      eval fix lands in a released ADK. The plan is to contribute this simplified
      leaf fix directly and subsume the stalled #5534.

ADK version pin: the replaced body is copied from google-adk 2.2.0
(``evaluation_generator.py`` lines 537-614). Re-verify against the source when
bumping ADK and refresh the copy if upstream changes the leaf.
# --- End monkey-patch ---
"""

import importlib
import logging
from typing import Any

from google.adk.apps.app import App
from google.adk.evaluation import evaluation_generator as _eg

logger = logging.getLogger(__name__)

_PATCHED_FLAG = "_app_aware_eval_patched"


def _resolve_package_app() -> App | None:
    """Return this package's ``App`` (the agent under eval), or ``None``.

    Mirrors ADK's own resolution (``getattr(agent_module.agent, "app", None)``)
    but sourced from this package so any un-threaded eval caller becomes
    App-aware. Resolved lazily at inference time (not at patch-apply time) so the
    package's lazy ``.env`` loading is not triggered early.
    """
    agent_module = importlib.import_module(f"{__package__}.agent")
    app = getattr(agent_module, "app", None)
    return app if isinstance(app, App) else None


async def _app_aware_generate_inferences_from_root_agent(
    root_agent: Any,
    user_simulator: Any,
    reset_func: Any = None,
    initial_session: Any = None,
    session_id: str | None = None,
    session_service: Any = None,
    artifact_service: Any = None,
    memory_service: Any = None,
    app: App | None = None,
) -> list[Any]:
    """App-aware replacement for ``_generate_inferences_from_root_agent``.

    Identical to the ADK 2.2.0 body except: it self-sources the package ``App``
    when ``app`` is ``None``, and builds the ``Runner`` from a copy of that ``App``
    (plugins merged, ``root_agent`` overridden) instead of the bare agent.
    """
    if app is None:
        app = _resolve_package_app()

    if not session_service:
        session_service = _eg.InMemorySessionService()

    if not memory_service:
        memory_service = _eg.InMemoryMemoryService()

    app_name = initial_session.app_name if initial_session else "EvaluationGenerator"
    user_id = initial_session.user_id if initial_session else "test_user_id"
    session_id = session_id if session_id else str(_eg.uuid.uuid4())

    _ = await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        state=initial_session.state if initial_session else {},
        session_id=session_id,
    )

    if not artifact_service:
        artifact_service = _eg.InMemoryArtifactService()

    if callable(reset_func):
        reset_func()

    request_intercepter_plugin = _eg._RequestIntercepterPlugin(
        name="request_intercepter_plugin"
    )
    ensure_retry_options_plugin = _eg.EnsureRetryOptionsPlugin(
        name="ensure_retry_options"
    )
    internal_eval_plugins = [request_intercepter_plugin, ensure_retry_options_plugin]

    if app is not None:
        runner_app = app.model_copy(
            update={
                "plugins": list(app.plugins) + internal_eval_plugins,
                "root_agent": root_agent,
            }
        )
        runner = _eg.Runner(
            app=runner_app,
            app_name=app_name,
            artifact_service=artifact_service,
            session_service=session_service,
            memory_service=memory_service,
        )
    else:
        runner = _eg.Runner(
            app_name=app_name,
            agent=root_agent,
            artifact_service=artifact_service,
            session_service=session_service,
            memory_service=memory_service,
            plugins=internal_eval_plugins,
        )

    generate_invocation = (
        _eg.EvaluationGenerator._generate_inferences_for_single_user_invocation
    )
    async with runner:
        events: list[Any] = []
        while True:
            next_user_message = await user_simulator.get_next_user_message(
                _eg.copy.deepcopy(events)
            )
            if next_user_message.status == _eg.UserSimulatorStatus.SUCCESS:
                async for event in generate_invocation(
                    runner, user_id, session_id, next_user_message.user_message
                ):
                    events.append(event)
            else:  # no message generated
                break

        app_details_by_invocation_id = (
            _eg.EvaluationGenerator._get_app_details_by_invocation_id(
                events, request_intercepter_plugin
            )
        )
        return _eg.EvaluationGenerator.convert_events_to_eval_invocations(
            events, app_details_by_invocation_id
        )


def apply_app_aware_eval_patch() -> None:
    """Install the App-aware eval-inference patch (idempotent)."""
    if getattr(_eg.EvaluationGenerator, _PATCHED_FLAG, False):
        return
    _eg.EvaluationGenerator._generate_inferences_from_root_agent = staticmethod(  # type: ignore[method-assign]
        _app_aware_generate_inferences_from_root_agent
    )
    setattr(_eg.EvaluationGenerator, _PATCHED_FLAG, True)
    logger.debug("Applied App-aware eval-inference patch to EvaluationGenerator.")
