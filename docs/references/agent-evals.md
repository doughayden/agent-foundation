# Agent Evals

Every agent-evaluation path this template ships, the command to run each, and where each artifact lives.

Agent behavior is the one thing unit and integration tests cannot catch, so this template ships a working slice of the full ADK eval surface: a deterministic PR gate plus runnable examples of judge metrics, rubric scoring, safety, and dynamic user-simulated conversations. ADK's [evaluation docs](https://adk.dev/evaluate/) are the source of truth for how evals work, and the [criteria reference](https://adk.dev/evaluate/criteria/) defines every metric. This page maps what is here and how to run it.

> [!NOTE]
> The eval lane calls Vertex AI and reads your ADC, so it cannot run as an autonomous Claude Code action: the command sandbox blocks the egress and credential read, and widening it would weaken the security posture. Run these commands yourself, or let CI run the gate.

## Prerequisites

- Vertex AI auth: a `.env` with `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and ADC (`gcloud auth application-default login`). This is the same setup as local development; see [Getting Started](../getting-started.md).
- The judge, safety, and multi-turn metrics and user-simulation case generation additionally use the paid Vertex Gen AI Evaluation Service; enable it in your project (an owner can, in one click). The deterministic gate needs none of this.

## What ships (`tests/eval/data/`)

| File | What it is |
|---|---|
| `template_agent.evalset.json` | The gate eval set: one single-turn tool-and-response case |
| `multi_turn.evalset.json` | A scripted multi-turn conversation case |
| `simple_time_query.test.json` | The `.test.json` single-file format, for `adk test` |
| `test_config.json` | Deterministic gate criteria |
| `full_eval_config.json` | Deep criteria: judge, rubric, hallucination, and safety metrics |
| `conversation_scenarios.json` | User-simulation scenarios (a pre-built and a custom persona) |
| `session_input.json` | Session seed for user-simulation cases |
| `user_sim_config.json` | User-simulation criteria plus simulator config |

`tests/unit/test_eval_artifacts.py` loads every file above through ADK's own schemas on each PR, so a malformed artifact fails fast in the unit lane with no LLM cost.

## Running evals

### The dev UI (start here): `uv run server`

`uv run server` is this template's replacement for `adk web`; with the web interface enabled it serves ADK's Eval and Trace tabs.

```bash
SERVE_WEB_INTERFACE=TRUE uv run server   # http://127.0.0.1:8000
```

In the UI, run the agent to create a session, open the Eval tab, click "Add current session" to capture it as an eval case, then run the case and compare actual against expected output. The Trace tab shows each turn's model request, response, and tool-call graph. Set `SERVE_WEB_INTERFACE=TRUE` in `.env` to make it the default. For the full click-by-click walkthrough (creating cases from sessions, editing them, and the Trace view), see the `adk web` workflow in ADK's [evaluation docs](https://adk.dev/evaluate/).

### The PR gate, locally: `uv run pytest tests/eval`

```bash
uv run pytest tests/eval
```

Calls `AgentEvaluator.evaluate()` against `test_config.json`, which raises on a sub-threshold metric. This is exactly what CI runs.

> [!WARNING]
> Never gate CI on the `adk eval` CLI. It exits 0 even when cases fail (verified against google-adk 2.2.0), so a CLI-based gate is silently always green. Only the pytest runner fails the build.

### The CLI: `adk eval`

```bash
# Gate criteria, with detailed per-metric output
adk eval src/agent_foundation tests/eval/data/template_agent.evalset.json \
  --config_file_path tests/eval/data/test_config.json --print_detailed_results

# The scripted multi-turn case
adk eval src/agent_foundation tests/eval/data/multi_turn.evalset.json \
  --config_file_path tests/eval/data/test_config.json

# Deep run: judge, rubric, hallucination, and safety metrics
adk eval src/agent_foundation tests/eval/data/template_agent.evalset.json \
  --config_file_path tests/eval/data/full_eval_config.json --print_detailed_results
```

Run a subset of cases with `<evalset>:<eval_id_1>,<eval_id_2>`.

### Test files: `adk test`

```bash
adk test tests/eval/data   # runs every *.test.json, criteria from the adjacent test_config.json
```

### Dynamic user simulation: `adk eval_set`

An LLM plays the user across a multi-turn conversation, following a plan and persona instead of a fixed script. Build an eval set from the shipped scenarios, then run it. Only `hallucinations_v1`, `safety_v1`, and the simulator and multi-turn metrics apply here, because there is no fixed expected response to match against.

```bash
adk eval_set create src/agent_foundation user_sim_demo
adk eval_set add_eval_case src/agent_foundation user_sim_demo \
  --scenarios_file tests/eval/data/conversation_scenarios.json \
  --session_input_file tests/eval/data/session_input.json
adk eval src/agent_foundation user_sim_demo \
  --config_file_path tests/eval/data/user_sim_config.json --print_detailed_results
```

`adk eval_set` writes the eval set to the agent package as `src/agent_foundation/<eval_set_id>.evalset.json` (gitignored as generated scratch; copy anything worth keeping into `tests/eval/data/`). To synthesize scenarios instead of writing them by hand:

```bash
adk eval_set generate_eval_cases src/agent_foundation user_sim_generated \
  --user_simulation_config_file generation_config.json
```

where `generation_config.json` looks like `{"count": 5, "model_name": "gemini-2.5-flash", "generation_instruction": "...", "environment_context": "..."}`. Generation uses the paid eval service. See ADK's [User Simulation](https://adk.dev/evaluate/user-sim/) guide for the persona model, the conversation-plan format, and the full simulator config.

### Migrating legacy eval data: `adk migrate`

Older non-pydantic eval files convert to the current schema with `adk migrate` (see the ADK docs).

## Metrics

The gate uses only judge-free, deterministic metrics; the deep and user-sim configs exercise the rest. The [ADK criteria reference](https://adk.dev/evaluate/criteria/) defines each one.

| Metric | Kind | Config | In gate |
|---|---|---|---|
| `tool_trajectory_avg_score` | deterministic | `test_config`, `full` | yes |
| `response_match_score` | deterministic (ROUGE-1) | `test_config`, `full` | yes |
| `final_response_match_v2` | LLM judge vs reference | `full` | no |
| `rubric_based_final_response_quality_v1` | LLM judge vs rubrics | `full` | no |
| `rubric_based_tool_use_quality_v1` | LLM judge vs rubrics | `full` | no |
| `hallucinations_v1` | LLM judge (groundedness) | `full`, `user_sim` | no |
| `safety_v1` | eval service | `full`, `user_sim` | no |
| `per_turn_user_simulator_quality_v1` | LLM judge | `user_sim` | no |
| `multi_turn_task_success_v1` | eval service | `user_sim` | no |

The `user_sim` config also references `multi_turn_trajectory_quality_v1` and `multi_turn_tool_use_quality_v1` (both eval-service, user-sim only). Reference-based metrics need an expected response, so they do not combine with user simulation.

## The CI gate

The `agent-eval` job in `.github/workflows/ci.yml` runs `uv run pytest tests/eval` on every PR that touches code, authenticating to Vertex AI with the dev environment's WIF principal. The always-run `status` sentinel requires it, so the existing `CI / status` required check blocks merges on eval failures with no separate registration. Only the deterministic config runs in CI; the judge, safety, and user-sim paths are for local and deep evaluation.

## Authoring and maintaining cases

1. Capture or write a case: `SERVE_WEB_INTERFACE=TRUE uv run server` (Eval tab), or hand-edit a file in `tests/eval/data/`.
2. Pin the expected tool trajectory (exact name and args) and a reference response built from stable tokens, no dates or clock values, so ROUGE stays stable against the real LLM.
3. Replay: `adk eval src/agent_foundation <evalset> --config_file_path tests/eval/data/test_config.json`.
4. Validate non-flaky: run `uv run pytest tests/eval` at least three times before relying on a new gate case.

See ADK's [evaluation docs](https://adk.dev/evaluate/) for the authoring workflow, the `EvalSet` schema, and migration utilities.

---

← [Back to References](README.md) | [Documentation](../README.md)
