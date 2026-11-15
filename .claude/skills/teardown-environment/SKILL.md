---
name: teardown-environment
description: Tear down one deployed environment (dev, stage or prod) by destroying its terraform/main resources while keeping its bootstrap root, registry and state bucket. Use when the user asks to destroy, tear down, decommission or reset an environment, to recover a half-finished destroy, or when a destroy fails on deletion protection, the Cloud SQL user, the service networking connection, the artifact bucket, Memory Bank memories or a subnetwork held by Cloud Run.
---

# Teardown Environment

Destroy one environment's `terraform/main` resources through `scripts/teardown.sh`. Each subcommand prints its evidence and ends with a `VERDICT:` line; act on the verdict, never on what you expect the step to do. The procedure, the blockers and why each fix is needed live in `docs/references/environment-teardown.md`; read it when the user asks why, or when a verdict is `FAILED`, `DRIFT` or `UNEXPECTED_CHANGES`.

> [!CAUTION]
> The destroy permanently deletes the environment's session database and its backups, Memory Bank memories and artifact objects. Confirm the environment name with the user before the first command, and get an explicit yes before every `--apply`.

## Inputs

- **Environment:** `dev`, `stage` or `prod`, matching a GitHub Environment that holds the deploy variables
- **Credentials:** `gh` authenticated for the repository, and Application Default Credentials with permission to delete the environment's resources (project Owner covers it)
- **Run outside the sandbox:** the script creates a git worktree and calls Google Cloud and GitHub

## Procedure

Run from the repository root. `--workdir` (default `$TMPDIR/teardown-ENV`) holds the worktree, the var file, saved plans and destroy logs.

```bash
S="${CLAUDE_SKILL_DIR}/scripts/teardown.sh"
$S prepare --env stage
$S unprotect --env stage            # review, ask, then: $S unprotect --env stage --apply
$S destroy --env stage              # review, ask, then: $S destroy --env stage --apply
$S wait-subnet --env stage          # only after VERDICT: SUBNET_HOLD, then destroy --apply again
$S verify --env stage
$S cleanup --env stage
```

| Step | Verdict | Next |
|---|---|---|
| `prepare` | `NO_DRIFT` | `unprotect` |
| | `PARTIAL` | An earlier destroy ran; go to `unprotect` (it skips targets already gone) or straight to `destroy` |
| | `DRIFT` | Stop. Show the plan lines and ask; the var file or the environment differs from `main` |
| `unprotect` | `READY_TO_UNPROTECT` | Show the targeted plan, ask, re-run with `--apply` |
| | `UNEXPECTED_CHANGES` | Stop. Never apply; report the listed changes |
| | `UNPROTECTED` / `NOTHING_TO_UNPROTECT` | `destroy` |
| `destroy` | `READY_TO_DESTROY` | Show the plan totals and the data it deletes, ask, re-run with `--apply` |
| | `DESTROYED` | `verify` |
| | `SUBNET_HOLD` | Tell the user Cloud Run releases the subnet within 1-2 hours; run `wait-subnet` in the background, then `destroy`, ask, `--apply` |
| | `FAILED` | Stop. Report each `Error` line; match it against the doc's blocker table |
| `verify` | `TORN_DOWN` | `cleanup` |
| | `RESOURCES_REMAIN` | Report what is left |
| | `UNVERIFIED` | A lookup failed (often expired credentials); fix access and re-run `verify` before reporting anything |

Rules that keep the run honest:

- **Before any `--apply`, check that deploys are held.** `prepare` prints the running `ci-cd.yml` runs; a merge run (dev, stage) or promotion (prod) during the teardown recreates resources. Ask the user to hold them.
- **Never edit Terraform files in the user's checkout.** The temporary edits exist only in the script's worktree, and `cleanup` discards them.
- **Report from script output only:** destroyed counts, remaining state and errors come from the `destroy` and `verify` lines, not from inference.

## Report

Close with the environment, each verdict in order, the destroy timing and counts, any wait for the subnet, and the `verify` lines. The environment comes back on its next normal deploy (merge run for dev and stage, promotion tag for prod).
