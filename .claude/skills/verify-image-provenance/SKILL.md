---
name: verify-image-provenance
description: Trace and verify Cloud Run image provenance through the digest chain (registry tag → OCI index → platform image → revision). Use whenever the user asks whether two revisions or deploys ran the same image, which commit produced a running image, why a registry tag digest differs from a Cloud Run revision digest, what an unknown/unknown platform artifact is, or when triaging a Cloud Run startup failure to distinguish a bad build from transient infrastructure — even if they don't say "digest" or "provenance".
---

# Verify Image Provenance

Answer image-identity questions about Cloud Run deployments with digest evidence rather than inference. One build pushes an OCI index (what tags and Terraform reference) wrapping a platform image (what revisions record) plus a provenance attestation — so the same artifact legitimately shows different digests on different surfaces. The conceptual taxonomy lives in `docs/references/image-digest-resolution.md`; read it if the user wants the *why* rather than a verdict.

The procedure is deterministic and runs fine on any model — for cheap unattended execution, delegate to a subagent with `model: haiku` and instruct it to follow this skill. Every factual claim in the report must trace to a script output line; if a prescribed mode fails, report the failure rather than inferring the answer another way.

## Inputs

Establish before running:

- **Project and region** — from the user, `.env`, `terraform/main` outputs, or `gcloud config`
- **Service name** — `${agent_name}-${environment}` (e.g. `my-agent-dev`)
- **What is being asked** — pick the matching mode below

If docker lacks registry auth, run `gcloud auth configure-docker ${REGION}-docker.pkg.dev` once.

## Procedure

Run `scripts/resolve_chain.sh` with the mode that matches the question. All modes are read-only.

| Question | Mode |
|---|---|
| "Is the deploy chain intact?" / general verification | `--service NAME` — verifies deployed index's amd64 child == latest ready revision's digest |
| "Did these two revisions/deploys run the same image?" | `--compare REV_A REV_B` |
| "What digest is revision X actually running?" | `--revision NAME` |
| "What does tag X point to?" / "what's in this index?" | `--tag TAG` (pass `--service NAME` or `--repo-uri URI`) |
| "What IS this digest/artifact?" (incl. unknown/unknown) | `--classify DIGEST` (pass `--service NAME` or `--repo-uri URI`) |
| "Which commit produced this running image?" | `--revision NAME` to get the platform digest, then `--find-commit DIGEST --service NAME` — the matching `{sha}` tag is the commit |
| "Which PR shipped this image?" | resolve the commit as above, then `gh api repos/{owner}/{repo}/commits/{sha}/pulls` (or read the `(#N)` ref in the squash-commit subject via `git log -1 {sha}`) |

Three findings are only valid when they come from script output — shortcuts on these produce confident wrong answers:

- **Commit attribution comes ONLY from a `--find-commit` match.** Never attribute an image to a commit via timestamps, "co-pushed" tags, deploy-time adjacency, or registry creation order — builds redeploy old digests and reruns re-push, so time correlation misattributes.
- **A digest from a revision spec is a platform image, never an index.** Label it accordingly.
- **"unknown/unknown" without a specific digest:** run `--tag` on a relevant tag (or `latest`) and read the children — the `unknown/unknown` entry users see in the registry UI is always the attestation child, never the index. Confirm with `--classify` on its digest.

```bash
.claude/skills/verify-image-provenance/scripts/resolve_chain.sh \
  --project PROJECT --region REGION --service SERVICE
```

For build-side corroboration (what a CI run exported), check the workflow log:

```bash
gh run view RUN_ID --log | grep -E "exporting manifest|CACHED"
```

`exporting manifest sha256:…` is the platform image, `exporting manifest list sha256:…` is the index. All-`CACHED` layers mean the run reproduced prior digests byte-identically.

## Interpreting Results

- **Tag digest ≠ revision digest is normal.** The tag names the index; the revision records the resolved `linux/amd64` child. Only an amd64-child mismatch (script verdict `MISMATCH`) indicates a real problem.
- **Identical platform digests across revisions are proof**, not coincidence — revision image fields are immutable. Two revisions with the same digest ran the same bytes; if one failed and one served, the failure was environmental, not the build.
- **`unknown/unknown` artifacts are provenance attestations** (BuildKit default), never deployed, not a problem.
- **`buildcache` tag is layer cache** (`mode=max`, includes builder-stage layers), overwritten per build, never deployed.

## Report Format

Lead with the verdict, then the evidence trace:

```text
Verdict: <answer to the user's question in one sentence>

Trace:
  tag {sha|version}        -> index sha256:aaaa…
    ├── linux/amd64        -> sha256:bbbb…   (recorded on revision(s) …)
    └── attestation        -> sha256:cccc…
  service deploys index    -> sha256:aaaa…
  revision runs platform   -> sha256:bbbb…   ✓ matches index child
```

Quote full digests at least once; truncate to 12 hex chars elsewhere. When the verdict is `MISMATCH`, say explicitly what to investigate (wrong image promoted, manual deploy outside CI, or registry tampering) rather than leaving the user with raw digests.
