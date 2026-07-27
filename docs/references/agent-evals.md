# Agent Evals

Every agent-evaluation path this template ships, the command to run each, and where each artifact lives.

We include a working slice of the full ADK eval surface: a deterministic PR gate plus runnable examples of judge metrics, rubric scoring, safety, and dynamic user-simulated conversations. ADK's [evaluation docs](https://adk.dev/evaluate/) are the source of truth for how evals work, and the [criteria reference](https://adk.dev/evaluate/criteria/) defines every metric. This page maps what is here and how to run it.

> [!NOTE]
> The eval lane calls Google APIs and reads your local ADC. AI code assistants may use a sandbox to block credential reads and network egress. Run the eval commands yourself to maintain security posture, or let CI run the gate.

## Prerequisites

- The same authentication as local development: a `.env` with `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and ADC (`gcloud auth application-default login`). See [Getting Started](../getting-started.md).
- The judge, safety, and multi-turn metrics and user-simulation case generation additionally use the [Gen AI evaluation service](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/evaluation-overview); enable it in your GCP project.

## App-aware execution

Eval inference runs the full `App` with its plugins applied, so evals score the same agent that `adk web` chat and the deployed server run, and LLM-judge metrics that read `app_details` get real context. Stock ADK eval unwraps to the bare `root_agent` and drops the wrapping `App`; a monkey-patch (`_eval_app_aware_patch.py`, applied at package import) restores App-aware execution. The patch is guarded by `except ModuleNotFoundError`, so it is a no-op in the production runtime image where eval dependencies are absent (and narrow enough that a renamed ADK symbol surfaces as a real error instead of silently disabling it). All four dev surfaces are App-aware: `uv run pytest tests/eval`, the `adk eval` CLI, the `adk web` eval tab, and `adk web` chat. The patch is removed once an App-aware fix lands in a released ADK — tracking [google/adk-python#5503](https://github.com/google/adk-python/issues/5503); the proposed upstream fix is [PR #6480](https://github.com/google/adk-python/pull/6480).

## What ships (`tests/eval/data/`)

| File | What it is |
|---|---|
| `template_agent.evalset.json` | The gate eval set: one single-turn tool-and-response case |
| `multi_turn.evalset.json` | A scripted multi-turn conversation case |
| `simple_time_query.test.json` | The `.test.json` single-file format, for `adk test` |
| `test_config.json` | Deterministic gate criteria |
| `full_eval_config.json` | Merge-gate criteria: judge, rubric, hallucination, and safety metrics |
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

### The PR gate, locally

```bash
uv run pytest tests/eval -m "deterministic"
```

Cases in the eval lane carry one of two pytest markers:

- `deterministic` — exact tool-trajectory plus ROUGE match against `test_config.json`. This is the PR gate.
- `judge` — LLM-judged, non-deterministic; `test_template_agent_judge_eval` scores against `full_eval_config.json` via `AgentEvaluator.evaluate_eval_set`.

Both markers run the agent with live model inference, so both need real credentials (the same `.env` and ADC as local development). The split is about scoring: `judge` additionally calls the paid Gen AI evaluation service, `deterministic` scores locally with exact-match and ROUGE.

```bash
uv run pytest tests/eval                      # both markers (the whole lane)
uv run pytest tests/eval -m "deterministic"   # the PR gate only
uv run pytest tests/eval -m "judge"           # LLM-judged deep evaluation only
```

The gate selects `-m "deterministic"` by explicit opt-in: a case joins the gate only when marked `deterministic`, so an unmarked live-model case can't leak cost or flakiness into the fast gate. It calls `AgentEvaluator.evaluate()` against `test_config.json`, which raises on a sub-threshold metric. The `judge` marker gets its own gate one step later, on merge to main. Both markers' tests run App-aware.

> [!WARNING]
> Never gate CI on the `adk eval` CLI. It exits 0 even when cases fail (verified against google-adk 2.2.0), so a CLI-based gate is silently always green. Only the pytest runner fails the build.

### Watching eval logs live

pytest captures logs and shows them only when a test fails, so a passing eval run is quiet. To watch each eval step as it happens (locally or in CI), raise the live-log level:

```bash
uv run pytest tests/eval -m "deterministic" --log-cli-level=DEBUG
```

`DEBUG` is the level that surfaces ADK's LLM request and response detail, the most useful eval output; `INFO` shows only higher-level lifecycle. It is verbose. To stream logs on every run instead of per-invocation, uncomment the `log_cli` block in `[tool.pytest.ini_options]` in `pyproject.toml`. In CI, append the flag to the eval step's command.

### Confirming what a run actually did

The loop over `num_runs` belongs to ADK's `AgentEvaluator`, which does not announce it, so the evidence that a run happened is the agent invocations themselves. Each one is bracketed by the logging callbacks in `callbacks.py`:

```
INFO agent_foundation.callbacks *** Starting agent 'your_agent' with invocation_id 'e-d4ba1ea5…' ***
INFO agent_foundation.callbacks *** Before LLM call … ***
INFO agent_foundation.callbacks *** Before invoking tool 'get_current_time' … ***
INFO agent_foundation.callbacks *** Leaving agent 'your_agent' with invocation_id 'e-d4ba1ea5…' ***
INFO google_adk…runners Runner closed.
```

One such block per run per eval case, each with its own `invocation_id`. Count them:

```bash
uv run pytest tests/eval -m "judge" --log-cli-level=INFO 2>&1 \
  | grep -c "Starting agent"          # JUDGE_NUM_RUNS per eval case
```

Scoring leaves its own trail, one block per run: `rouge_scorer: Using default tokenizer` for the ROUGE metric, and `vertexai…_evals_common: Evaluation run completed.` with a duration for each eval-service metric pass. Counting either cross-checks the inference count.

Count the invocations rather than trusting the constant: `JUDGE_NUM_RUNS` states what was asked for, while the invocation IDs are what ADK actually ran.

### The CLI: `adk eval`

The `adk` commands take the agent package directory. Set it once (the template has a single package under `src/`); the later examples reuse it:

```bash
# The agent package dir (single package under src/)
AGENT_PACKAGE=$(basename src/*/)

# Gate criteria, with detailed per-metric output
adk eval src/$AGENT_PACKAGE tests/eval/data/template_agent.evalset.json \
  --config_file_path tests/eval/data/test_config.json --print_detailed_results

# The scripted multi-turn case
adk eval src/$AGENT_PACKAGE tests/eval/data/multi_turn.evalset.json \
  --config_file_path tests/eval/data/test_config.json

# Deep run: judge, rubric, hallucination, and safety metrics
adk eval src/$AGENT_PACKAGE tests/eval/data/template_agent.evalset.json \
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
adk eval_set create src/$AGENT_PACKAGE user_sim_demo
adk eval_set add_eval_case src/$AGENT_PACKAGE user_sim_demo \
  --scenarios_file tests/eval/data/conversation_scenarios.json \
  --session_input_file tests/eval/data/session_input.json
adk eval src/$AGENT_PACKAGE user_sim_demo \
  --config_file_path tests/eval/data/user_sim_config.json --print_detailed_results
```

`adk eval_set` writes the eval set to the agent package as `src/$AGENT_PACKAGE/<eval_set_id>.evalset.json` (gitignored as generated scratch; copy anything worth keeping into `tests/eval/data/`). To keep generated eval sets out of the package entirely, pass `--eval_storage_uri gs://<bucket>` to every `adk eval_set` command and to `adk eval`; the eval set is then stored in and read from that GCS bucket. A cloud bucket is the only storage override, local paths are not configurable.

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

The PR gate uses only judge-free, deterministic metrics; the merge gate adds the judged and eval-service ones, and the user-sim config exercises the rest. The [ADK criteria reference](https://adk.dev/evaluate/criteria/) defines each one.

| Metric | Kind | Config | Gate |
|---|---|---|---|
| `tool_trajectory_avg_score` | deterministic | `test_config` | PR |
| `response_match_score` | deterministic (ROUGE-1) | `test_config` | PR |
| `final_response_match_v2` | LLM judge vs reference | not shipped | none |
| `rubric_based_final_response_quality_v1` | LLM judge vs rubrics | `full` | merge |
| `rubric_based_tool_use_quality_v1` | LLM judge vs rubrics | `full` | merge |
| `hallucinations_v1` | LLM judge (groundedness) | `full`, `user_sim` | merge |
| `safety_v1` | eval service | `full`, `user_sim` | merge |
| `per_turn_user_simulator_quality_v1` | LLM judge | `user_sim` | none |
| `multi_turn_task_success_v1` | eval service | `user_sim` | none |
| `multi_turn_trajectory_quality_v1` | eval service | `user_sim` | none |
| `multi_turn_tool_use_quality_v1` | eval service | `user_sim` | none |

"Merge" means the `judge-eval` job on merge to main, which scores `full_eval_config.json`. The two deterministic criteria are deliberately not in that file: the PR gate already scores them, and re-scoring them at `JUDGE_NUM_RUNS` would quietly make an exact-match threshold demand five perfect runs where the PR gate demands two, a merge-only failure the PR gate could never reproduce. It blocks only in production mode. `final_response_match_v2` is listed for reference but is deliberately absent from the shipped config, for the reason in "Limits and gotchas" below.

Reference-based metrics need an expected response, so they do not combine with user simulation.

## The CI gates

Two gates run in CI, at two different points, both authenticating to Vertex AI with the dev environment's WIF principal.

**Deterministic, on every PR.** The `agent-eval` job in `.github/workflows/ci.yml` runs `uv run pytest tests/eval -m "deterministic"` on every PR that touches code. The always-run `status` sentinel requires it, so the existing `CI / status` required check blocks merges on eval failures with no separate registration.

**Judge, on every merge to main.** The `judge-eval` job in `.github/workflows/ci-cd.yml` calls the reusable `judge-eval.yml` workflow. It runs in-process, so it needs no deployed revision and starts without waiting on a deploy. The workflow runs the lane in two steps:

1. `pytest tests/eval -m "judge and liveness"` — the model-endpoint liveness probes, always blocking.
2. `pytest tests/eval -m "judge and not liveness"` — the scored eval, where the deployment mode decides whether a failure blocks.

Splitting them is what makes the second step's exit code readable. Exit 1 means a sub-threshold score and nothing else: the preflight has ruled out a dead endpoint, and the judge test converts every non-assertion failure (a missing eval extra, an empty dataset, an eval-service error) into `EVAL_ERROR_EXIT_CODE`. Every other non-zero code is a broken run and fails the job in either mode. Note that a job timeout and a failed preflight are job failures, not exit codes, so `gating: false` cannot absorb those either. Locally the whole lane still runs as one session, where a failed probe arms `session.shouldfail` to abort before the paid tests.

Mode decides how the scored step's failure is treated:

- **Dev-only mode** (the default): signal only. A sub-threshold score is reported in the job summary and as a warning annotation, then the job exits 0. A failed preflight or a broken run still fails, so a dead endpoint is never mistaken for a passing gate.
- **Production mode**: blocking. A sub-threshold score fails the job, and `require-stage-success` requires that job's conclusion at tag time, so a behavioral regression blocks the prod tag for that commit. Stage has already deployed by then and is not reverted.

The judge gate is off the PR path deliberately: it is non-deterministic and calls the paid Gen AI evaluation service, so it belongs where a failure is investigated rather than where it would flake a merge queue. The user-simulation paths stay local and manual.

`judge-eval` runs only when `ci-cd.yml` itself triggers, so a merge touching nothing under its path filter produces no judge run. That includes a change to `tests/eval/` alone, which is the change most likely to alter what the gate asserts. Adding `tests/eval/**` to the filter would fix that but would also build and deploy unchanged source on every eval-data merge, so the tradeoff is tracked in issue #238 rather than settled here. In production mode, tagging a commit whose merge triggered no run fails `require-stage-success` closed on a missing run.

### Varying a run

What a run scores is fixed in `tests/eval/test_agent_eval.py`: the eval set path, the judge config path, and the per-gate run counts are module constants. There are no workflow inputs or environment variables for them, so CI and a local run always score the same thing, and the command you run locally is the command CI runs.

```python
DETERMINISTIC_NUM_RUNS = 2
JUDGE_NUM_RUNS = 5
```

The judge gate averages more runs because its metrics return a binary verdict each time. At 2 the only achievable scores are 0, 0.5, and 1, so every threshold above 0.5 silently demands unanimity; 5 gives the average enough resolution for a `0.7` to mean "four of five". The deterministic gate keeps 2: exact trajectory matching wants unanimity regardless, and ROUGE produces continuous per-run scores that average sensibly at any sample size. ADK runs the passes serially, so raising `JUDGE_NUM_RUNS` costs proportional wall clock on every merge.

To vary either one, edit the constant. That is a reviewable diff in the same file as the eval cases, rather than a value threaded through a workflow input.

**Stress-test by looping, not by raising the count.** Repeated runs at the shipped setting measure flakiness better than one run at a higher setting, because a marginal metric passes a high-`num_runs` invocation while still sitting one bad draw from red.

```bash
# Five invocations, each scoring JUDGE_NUM_RUNS passes per case
for i in 1 2 3 4 5; do uv run pytest tests/eval -m "judge" -q || echo "RUN $i FAILED"; done
```

If you want the harshest signal, temporarily drop `JUDGE_NUM_RUNS` to 2 and loop: at 2 a single bad draw scores 0.5 and fails, so repeated green proves every individual run was unanimous. Put it back before committing.

## Authoring and maintaining cases

1. Capture or write a case: `SERVE_WEB_INTERFACE=TRUE uv run server` (Eval tab), or hand-edit a file in `tests/eval/data/`.
2. Pin the expected tool trajectory (exact name and args) and a reference response built from stable tokens, no dates or clock values, so ROUGE stays stable against the real LLM.
3. Replay: `adk eval src/$AGENT_PACKAGE <evalset> --config_file_path tests/eval/data/test_config.json`.
4. Validate: run `uv run pytest tests/eval -m "deterministic"` at least three times before relying on a new gate case. For a case the judge gate will score, loop `-m "judge"` rather than raising the run count — see "Stress-test by looping" above.

See ADK's [evaluation docs](https://adk.dev/evaluate/) for the authoring workflow, the `EvalSet` schema, and migration utilities.

## Limits and gotchas

- **Cross-session memory is not eval-testable.** Each eval case runs in a fresh in-memory session, so behavior that depends on a separate prior session, like memory recall across sessions, cannot be exercised here. Cover that continuity with an integration test instead.
- **The gate's tool match is exact, by design.** `tool_trajectory_avg_score` matches tool name and args exactly (`IN_ORDER` only tolerates extra calls). That is deliberate: it is the only judge-free, deterministic option that scores at no added cost (beyond the agent's own inference), which is what a per-PR gate needs. For semantic tool-use scoring that tolerates reordered or alternative tool paths, use the rubric metrics in `full_eval_config.json`, which an LLM judge scores on every merge rather than on every PR. Match the metric to the gate: strict and cheap per PR, rubric and non-deterministic per merge.
- **A reference-based judge cannot score a case whose answer is not deterministic.** `final_response_match_v2` asks an LLM whether the response matches the case's `expected_response`. That only works when the correct answer is stable enough to write down. Our gate case asks for the current time, and the guidance above says to build the reference from stable tokens with no clock values so ROUGE stays stable, so the reference names the timezone but never states a time while every actual response does. The judge has no stable basis for a verdict and splits roughly evenly: measured over four runs, exactly one of each pair passed every time, scoring 0.5 against a 0.7 threshold, with the verdict uncorrelated with any observable difference (the ISO-formatted answer failed in one run and passed in another). This is why `final_response_match_v2` is not in `full_eval_config.json`. A ROUGE gate wants a clock-free reference and a semantic judge wants a complete one; one case cannot serve both. Reference-free metrics (the rubric, hallucination, and safety ones) score this case stably, and a fork whose agent has deterministic answers can add `final_response_match_v2` back.
- **Text emitted before a tool call is not judged by default.** ADK hands an LLM-judge metric only the invocation's `final_response`, so for an agent that greets before calling a tool and answers after, the greeting is invisible to the judge. If a reference or rubric covers the whole turn, set `include_intermediate_responses_in_final: true` on that criterion to concatenate the intermediate text before judging. This agent has that shape (its instructions say to greet by name).
- **Thinking models may skip tools.** A model with thinking enabled can answer without calling a tool, which fails an exact-trajectory case. If you hit this, set `tool_config` to `mode="ANY"` on the agent, or use a non-thinking model for the evaluated path.
- **`num_runs` quantizes the score, so a low threshold can still mean unanimity.** Metrics that return a binary per-run verdict (the judge metrics observed here do) are averaged across `num_runs`. At 2 runs the only achievable scores are 0, 0.5, and 1, so every threshold above 0.5 requires both to pass. A `0.7` threshold reads like it tolerates a bad draw and does not. This is why `JUDGE_NUM_RUNS` is 5 while `DETERMINISTIC_NUM_RUNS` is 2: at 5 runs, `0.7` means four of five. Resolution costs proportionally more inference on every gated run, so it is a deliberate tradeoff per gate, not a number to raise reflexively.
- **Groundedness is scored against tool output, so a tool that under-reports produces "hallucinations".** `hallucinations_v1` classifies each response sentence as supported, unsupported, or contradictory against the context, and is instructed not to apply world knowledge unless trivial. A value the model can derive but the tool never returned reads as unsupported. `get_current_time` returns `timezone_abbreviation` for exactly this reason: the model renders times in prose as "3:39 PM EDT", and without the abbreviation in the result that answer is ungrounded. Grounding a value the tool cannot actually source is worse than omitting it, so that field is `None` for the roughly 39% of IANA zones tzdata renders numerically (`Asia/Ho_Chi_Minh` reports `+07`, not `ICT`) and the docstring tells the model to name the offset instead. When this metric fails, check whether the tool result actually contains what the answer asserts before touching the metric.
- **Never lower the bar to pass.** Dropping a threshold or deleting a flaky case hides a real regression. Fix the agent (instructions, tools) or stabilize the case (stable reference tokens, `temperature=0`), not the gate.
- **Eval cases reference the agent by app name.** Each case's `session_input.app_name` must match the agent's `App(name=...)`, or the run fails with "Session not found". The shipped cases already match; keep them aligned if you rename the app.
- **Eval-service metrics default to the global endpoint.** The Vertex-backed metrics (`safety_v1`, `multi_turn_*`) do not inherit `GOOGLE_CLOUD_LOCATION`; the service supports only a region subset. You normally configure nothing; override only for data residency.

## Relationship to the Agent Platform Eval SDK

This template uses ADK-native evaluation deliberately. ADK's evaluator ships in `google-adk` (which the agent already depends on) and consumes ADK's own `EvalSet` schema with no adapter: the deterministic gate metrics (`tool_trajectory_avg_score`, ROUGE `response_match_score`) are local Python scorers, and the `*_v1` metrics delegate to the Vertex AI evaluation service.

Google's `agents-cli` is a productivity layer over the Agent Platform Eval SDK. For most of its eval surface (run, grade, author, user simulation, optimize, custom metrics) it overlaps what `adk eval` already does natively; its non-overlapping value, regression-diff and failure-clustering across many runs, is scaled-suite tooling. Its `EvaluationDataset` schema and configs are not interchangeable with ADK's `EvalSet`. This template stays on `adk eval` because it is the base primitive shipped in `google-adk`, and it uniquely provides free, deterministic, local scorers (`tool_trajectory_avg_score`, ROUGE) suited to a per-PR gate: the gate still pays for the agent's live model inference, but the scoring itself adds no cost or nondeterminism, where `agents-cli`'s managed metrics would add both on top. ADK's eval is also the more mature of the two front-ends.

A project that grows a large, judge-heavy eval suite and needs regression-diff (scoring deltas between two result sets) or failure-clustering should reach for the Agent Platform Eval SDK directly (`google-cloud-aiplatform[evaluation]`) or `agents-cli` at that point; both are out of scope for this template.

---

← [Back to References](README.md) | [Documentation](../README.md)
