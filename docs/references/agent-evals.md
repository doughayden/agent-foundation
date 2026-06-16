# Agent Evals

Every agent-evaluation path this template ships, the command to run each, and where each artifact lives.

We include a working slice of the full ADK eval surface: a deterministic PR gate plus runnable examples of judge metrics, rubric scoring, safety, and dynamic user-simulated conversations. ADK's [evaluation docs](https://adk.dev/evaluate/) are the source of truth for how evals work, and the [criteria reference](https://adk.dev/evaluate/criteria/) defines every metric. This page maps what is here and how to run it.

> [!NOTE]
> The eval lane calls Google APIs and reads your local ADC. AI code assistants may use a sandbox to block credential reads and network egress. Run the eval commands yourself to maintain security posture, or let CI run the gate.

## Prerequisites

- The same authentication as local development: a `.env` with `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and ADC (`gcloud auth application-default login`). See [Getting Started](../getting-started.md).
- The judge, safety, and multi-turn metrics and user-simulation case generation additionally use the [Gen AI evaluation service](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/evaluation-overview); enable it in your GCP project.

## What ships (`eval/data/`)

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

### The PR gate, locally: `uv run pytest eval`

```bash
uv run pytest eval
```

Calls `AgentEvaluator.evaluate()` against `test_config.json`, which raises on a sub-threshold metric. This is exactly what CI runs.

> [!WARNING]
> Never gate CI on the `adk eval` CLI. It exits 0 even when cases fail (verified against google-adk 2.2.0), so a CLI-based gate is silently always green. Only the pytest runner fails the build.

### The CLI: `adk eval`

The `adk` commands take the agent package directory. Set it once (the template has a single package under `src/`); the later examples reuse it:

```bash
# The agent package dir (single package under src/)
AGENT_PACKAGE=$(basename src/*/)

# Gate criteria, with detailed per-metric output
adk eval src/$AGENT_PACKAGE eval/data/template_agent.evalset.json \
  --config_file_path eval/data/test_config.json --print_detailed_results

# The scripted multi-turn case
adk eval src/$AGENT_PACKAGE eval/data/multi_turn.evalset.json \
  --config_file_path eval/data/test_config.json

# Deep run: judge, rubric, hallucination, and safety metrics
adk eval src/$AGENT_PACKAGE eval/data/template_agent.evalset.json \
  --config_file_path eval/data/full_eval_config.json --print_detailed_results
```

Run a subset of cases with `<evalset>:<eval_id_1>,<eval_id_2>`.

### Test files: `adk test`

```bash
adk test eval/data   # runs every *.test.json, criteria from the adjacent test_config.json
```

### Dynamic user simulation: `adk eval_set`

An LLM plays the user across a multi-turn conversation, following a plan and persona instead of a fixed script. Build an eval set from the shipped scenarios, then run it. Only `hallucinations_v1`, `safety_v1`, and the simulator and multi-turn metrics apply here, because there is no fixed expected response to match against.

```bash
adk eval_set create src/$AGENT_PACKAGE user_sim_demo
adk eval_set add_eval_case src/$AGENT_PACKAGE user_sim_demo \
  --scenarios_file eval/data/conversation_scenarios.json \
  --session_input_file eval/data/session_input.json
adk eval src/$AGENT_PACKAGE user_sim_demo \
  --config_file_path eval/data/user_sim_config.json --print_detailed_results
```

`adk eval_set` writes the eval set to the agent package as `src/$AGENT_PACKAGE/<eval_set_id>.evalset.json` (gitignored as generated scratch; copy anything worth keeping into `eval/data/`). To keep generated eval sets out of the package entirely, pass `--eval_storage_uri gs://<bucket>` to every `adk eval_set` command and to `adk eval`; the eval set is then stored in and read from that GCS bucket. A cloud bucket is the only storage override, local paths are not configurable.

To synthesize scenarios instead of writing them by hand:

```bash
adk eval_set generate_eval_cases src/$AGENT_PACKAGE user_sim_generated \
  --user_simulation_config_file generation_config.json
```

where `generation_config.json` looks like `{"count": 5, "model_name": "gemini-2.5-flash", "generation_instruction": "...", "environment_context": "..."}`. Generation uses the paid GCP Gen AI evaluation service. See ADK's [User Simulation](https://adk.dev/evaluate/user-sim/) guide for the persona model, the conversation-plan format, and the full simulator config.

### Optimizing prompts: `adk optimize`

ADK ships a GEPA prompt optimizer that rewrites the root agent's instructions against a target metric, driven by an optimizer config file:

```bash
adk optimize src/$AGENT_PACKAGE <optimizer_config_path>
```

It is long-running and makes multiple LLM calls. Treat it as a last resort after manual instruction fixes, and run a single pass rather than looping on it. See `adk optimize --help` for the config format.

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
| `multi_turn_trajectory_quality_v1` | eval service | `user_sim` | no |
| `multi_turn_tool_use_quality_v1` | eval service | `user_sim` | no |

Reference-based metrics need an expected response, so they do not combine with user simulation.

## The CI gate

The `agent-eval` job in `.github/workflows/ci.yml` runs `uv run pytest eval` on every PR that touches code, authenticating to Vertex AI with the dev environment's WIF principal. The always-run `status` sentinel requires it, so the existing `CI / status` required check blocks merges on eval failures with no separate registration. Only the deterministic config runs in CI; the judge, safety, and user-sim paths are for local and deep evaluation.

## Authoring and maintaining cases

1. Capture or write a case: `SERVE_WEB_INTERFACE=TRUE uv run server` (Eval tab), or hand-edit a file in `eval/data/`.
2. Pin the expected tool trajectory (exact name and args) and a reference response built from stable tokens, no dates or clock values, so ROUGE stays stable against the real LLM.
3. Replay: `adk eval src/$AGENT_PACKAGE <evalset> --config_file_path eval/data/test_config.json`.
4. Validate non-flaky: run `uv run pytest eval` at least three times before relying on a new gate case.

See ADK's [evaluation docs](https://adk.dev/evaluate/) for the authoring workflow, the `EvalSet` schema, and migration utilities.

## Limits and gotchas

- **Cross-session memory is not eval-testable.** Each eval case runs in a fresh in-memory session, so behavior that depends on a separate prior session, like memory recall across sessions, cannot be exercised here. Cover that continuity with an integration test instead.
- **The gate's tool match is exact, by design.** `tool_trajectory_avg_score` matches tool name and args exactly (`IN_ORDER` only tolerates extra calls). That is deliberate: it is the only judge-free, zero-cost, deterministic option for a per-PR gate. For semantic tool-use scoring that tolerates reordered or alternative tool paths, use the rubric metrics in `full_eval_config.json` (LLM judge, not gate-able). Match the metric to the context: strict for the gate, rubric for deep evaluation.
- **Thinking models may skip tools.** A model with thinking enabled can answer without calling a tool, which fails an exact-trajectory case. If you hit this, set `tool_config` to `mode="ANY"` on the agent, or use a non-thinking model for the evaluated path.
- **Never lower the bar to pass.** Dropping a threshold or deleting a flaky case hides a real regression. Fix the agent (instructions, tools) or stabilize the case (stable reference tokens, `temperature=0`), not the gate.
- **Eval cases reference the agent by app name.** Each case's `session_input.app_name` must match the agent's `App(name=...)`, or the run fails with "Session not found". The shipped cases already match; keep them aligned if you rename the app.
- **Eval-service metrics default to the global endpoint.** The Vertex-backed metrics (`safety_v1`, `multi_turn_*`) do not inherit `GOOGLE_CLOUD_LOCATION`; the service supports only a region subset. You normally configure nothing; override only for data residency.

## Relationship to the Agent Platform Eval SDK

This template uses ADK-native evaluation deliberately. ADK's evaluator ships in `google-adk` (which the agent already depends on) and consumes ADK's own `EvalSet` schema with no adapter: the deterministic gate metrics (`tool_trajectory_avg_score`, ROUGE `response_match_score`) are local Python scorers, and the `*_v1` metrics delegate to the Vertex AI evaluation service.

Google's `agents-cli` is a productivity layer over the Agent Platform Eval SDK. For most of its eval surface (run, grade, author, user simulation, optimize, custom metrics) it overlaps what `adk eval` already does natively; its non-overlapping value, regression-diff and failure-clustering across many runs, is scaled-suite tooling. Its `EvaluationDataset` schema and configs are not interchangeable with ADK's `EvalSet`. This template stays on `adk eval` because it is the base primitive shipped in `google-adk`, and it uniquely provides free, deterministic, local scorers (`tool_trajectory_avg_score`, ROUGE) suited to a zero-cost per-PR gate, where `agents-cli`'s managed metrics would add cost and nondeterminism. ADK's eval is also the more mature of the two front-ends.

A project that grows a large, judge-heavy eval suite and needs regression-diff (scoring deltas between two result sets) or failure-clustering should reach for the Agent Platform Eval SDK directly (`google-cloud-aiplatform[evaluation]`) or `agents-cli` at that point; both are out of scope for this template.

---

← [Back to References](README.md) | [Documentation](../README.md)
