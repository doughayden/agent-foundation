---
name: sync-foundation
description: |
  Interactive workflow for syncing upstream agent-foundation enhancements to a downstream project.
  Guides through IDE diff review, selective file checkout, and manual adaptation with HITL checkpoints.
argument-hint: "[version] (e.g., v0.12.0)"
---

ultrathink

## Mission

Guide the user through syncing upstream agent-foundation template enhancements to their downstream project. This is a **collaborative, human-in-the-loop workflow** — every file sync decision requires explicit user approval.

**Key Characteristics:**
- **Phase-ordered review**: Core code patterns first, docs last (see Phase Ordering Rationale)
- **Per-file HITL**: IDE diff review, ask user action, execute
- **Two sync modes**: "Review & adapt" (manual) for code patterns, "Checkout & restore" for infra/CI/docs
- **Resumable**: Task list tracks progress across phases
- **Unstaged accumulation**: All changes stay unstaged until the user requests a commit

**Phase Ordering Rationale:**
Code patterns first because they're the core value and inform everything else. Dependencies before infra because infra may depend on new services/APIs. Infra before CI/CD because CI/CD deploys what infra defines. Docs last because they describe everything else.

## Prerequisites

1. Working directory is a downstream project derived from agent-foundation
2. The `foundation` git remote exists (if not, skill helps configure it)
3. Clean working tree (or user acknowledgment of uncommitted changes)

## Task List Usage

**Create task list at phase start for progress tracking and resumability:**
- Use TaskCreate for all phase steps before starting work
- Mark tasks in_progress when starting, completed when done
- If interrupted, resume from task list state

## IDE Diff Pattern

**This is the primary review tool for all phases.** For core code files (different package paths), export the foundation version to `/tmp/` and open a side-by-side diff in the user's IDE.

**Supported diff commands** (detected in Phase 0, stored as `DIFF_CMD`):
- **VS Code:** `code --diff <left> <right>`
- **Cursor:** `cursor --diff <left> <right>`
- **JetBrains (IntelliJ, PyCharm, etc.):** `idea diff <left> <right>` (or `pycharm`, `webstorm`, etc.)
- **Terminal fallback:** `diff --color -u <left> <right> | less -R`

```bash
# Export foundation version
git show foundation-tags/$VERSION:src/agent_foundation/<file> > /tmp/foundation-<file>

# Open diff: downstream (left) vs foundation (right)
# Green additions on the right = what upstream brings
$DIFF_CMD /path/to/downstream/<file> /tmp/foundation-<file>
```

**Direction matters:** Always show the downstream project on the left and foundation on the right. This way, green additions represent what upstream brings — the natural mental model for a sync.

For files with matching paths (Terraform, CI/CD, docs), the diff can also be shown after checkout:

```bash
# After checkout, show what changed
$DIFF_CMD <file> /tmp/foundation-<file>
```

**Dual review:** Always review diffs yourself (using `diff`, `git diff`, or whatever tool gives the best signal) to make informed recommendations. The IDE diff is for the user's visual review — it does not replace your own analysis.

## File-Level STOP Gate

For every file diff shown, use this consistent interaction pattern:

1. Review the diff yourself and form a recommendation
2. Open the IDE diff for the user
3. State which file this is, its role, and what the upstream changes are
4. Present action options appropriate to the phase
5. **STOP** and wait for user decision
6. Execute the chosen action
7. Move to next file

**Never batch multiple file decisions into one prompt. One file, one decision.**

## Workflow

### Phase 0: Orientation

**Goal:** Build a mental model of what changed before diving into file-level diffs.

1. **Verify foundation remote:**
   ```bash
   git remote -v | grep foundation
   ```
   If missing, help user set it up:
   ```bash
   git remote add foundation <upstream-url>
   ```

2. **Detect diff tool:** Check which IDE CLI is available and set `DIFF_CMD` for the session:
   ```bash
   # Detect in preference order
   if command -v code &>/dev/null; then DIFF_CMD="code --diff"
   elif command -v cursor &>/dev/null; then DIFF_CMD="cursor --diff"
   elif command -v idea &>/dev/null; then DIFF_CMD="idea diff"
   elif command -v pycharm &>/dev/null; then DIFF_CMD="pycharm diff"
   else DIFF_CMD="diff --color -u"; fi
   echo "Diff tool: $DIFF_CMD"
   ```
   If auto-detection picks the wrong tool, ask the user which to use.

3. **Fetch foundation tags:**
   ```bash
   git fetch foundation 'refs/tags/*:refs/foundation-tags/*' --no-tags
   ```

4. **List available versions:**
   ```bash
   git for-each-ref refs/foundation-tags --format='%(refname:short) | %(creatordate:short)' --sort=-version:refname | head -10
   ```

5. **Set target version:**
   - If user provided `$ARGUMENTS`, use that as `VERSION`
   - Otherwise, **STOP** and ask user which version to sync

6. **Identify last sync point:**
   ```bash
   git log --oneline --grep="foundation" --grep="sync" --all-match -5
   ```

7. **Show what changed** (changelog + commit log):
   ```bash
   # Show changelog for this version
   git show foundation-tags/$VERSION:CHANGELOG.md

   # Show commits since previous sync version
   git log --oneline foundation-tags/<previous>..foundation-tags/$VERSION
   ```

8. **Show high-level diff stats** (everything except src/ and tests/):
   ```bash
   git diff --stat HEAD..foundation-tags/$VERSION -- . ':!src/' ':!tests/'
   ```

9. **Identify downstream package name** by inspecting `src/`:
   ```bash
   ls src/
   ```
   Store as `DOWNSTREAM_PKG` for cross-package diffs in Phases 1-2.

10. **Identify downstream-specific files** that will show as deletions but must be preserved. List these explicitly in the orientation summary.

11. **STOP**: Present the orientation summary to user. Ask if ready to proceed.

12. **Create sync branch:**
    ```bash
    git checkout main && git pull origin main
    git checkout -b sync/foundation-$VERSION
    ```

### Phase 1: Core Code Patterns (Review & Adapt)

**Goal:** Review improvements in foundation's core modules. These are **reference implementations** — the user adapts patterns to their downstream code manually, since package names differ.

**Mode: IDE diff review + manual edits.** No `git checkout` — package paths differ (`agent_foundation` vs downstream name).

Review each file individually. For each file, open the IDE diff and **STOP** for user decision.

**Review order** (most impactful first):
1. `src/agent_foundation/utils/config.py` — Pydantic config patterns
2. `src/agent_foundation/utils/observability.py` — OpenTelemetry patterns
3. `src/agent_foundation/server.py` — FastAPI/ADK server setup
4. `src/agent_foundation/agent.py` — Agent configuration
5. `src/agent_foundation/callbacks.py` — Lifecycle callbacks
6. `src/agent_foundation/tools.py` — Tool patterns
7. `src/agent_foundation/prompt.py` — Instruction provider patterns
8. `src/agent_foundation/__init__.py` — Export/lazy-loading patterns

**For each file:**

First check if there are meaningful changes using a cross-package diff:

```bash
diff <(cat src/$DOWNSTREAM_PKG/<file>) <(git show foundation-tags/$VERSION:src/agent_foundation/<file>)
```

If the diff is empty, skip silently. If non-empty, open IDE diff and **STOP** with options:
- **Skip** — No changes needed in downstream
- **Note for later** — User will adapt manually after the sync workflow
- **Apply now** — Apply edits to the downstream equivalent immediately

When applying: make targeted edits preserving downstream-specific code (additional models, validators, properties, etc.). **Update corresponding tests in the same step** — don't defer test fixes to wrap-up.

> After reviewing all files, summarize which had changes and what the user decided for each.

### Phase 2: Test Infrastructure (Sync & Adapt)

**Goal:** Keep downstream `tests/conftest.py` fixtures aligned with foundation, enabling bulk sync of test modules that test foundation components.

**Why this matters:** Foundation's `conftest.py` defines mock classes (MockState, MockContent, MockSession, MockReadonlyContext, MockMemoryCallbackContext, etc.) and factory fixtures that mock ADK interfaces — not project-specific code. When these fixtures stay in sync, entire test modules for unchanged foundation components can be synced directly with only an import path substitution. This compounding benefit grows with each sync — the more fixtures you keep aligned, the less manual test work each sync requires.

**Sync strategy — two tiers:**

1. **Foundation fixtures (sync):** Mock classes and factory fixtures that mirror ADK interfaces. These should match foundation exactly. Diff and sync, preserving only the downstream package import path.

2. **Downstream fixtures (preserve):** Fixtures for project-specific tools, callbacks, or models. These are additive — foundation won't have them, so `git checkout` won't touch them.

**Workflow:**

1. Open IDE diff for `tests/conftest.py` and **STOP** for user decision.

2. When syncing: apply foundation's fixture changes, keeping downstream-only fixtures intact. All `agent_foundation` references must be replaced with `$DOWNSTREAM_PKG` — this includes both import statements (`from $DOWNSTREAM_PKG...`) and mock patch targets (`mocker.patch("$DOWNSTREAM_PKG...")`). A missed patch target silently mocks nothing and produces false-passing tests.

3. **After conftest sync, identify test modules eligible for bulk sync.** These are test files for foundation components unlikely to change downstream:
   ```bash
   # List foundation test files
   git show foundation-tags/$VERSION:tests/ | grep "^test_"

   # For each, check if the downstream equivalent only differs by import path
   diff <(sed "s/agent_foundation/$DOWNSTREAM_PKG/g" <(git show foundation-tags/$VERSION:tests/<test_file>)) tests/<test_file>
   ```

4. For test modules with minimal or no diff after import substitution, offer to **sync the test file** (checkout + sed replace package name in both imports and patch targets). After substitution, verify no `agent_foundation` references remain:
   ```bash
   grep -n "agent_foundation" tests/<test_file>
   ```
   For test modules with significant downstream customization, use the IDE diff-and-STOP pattern from Phase 1.

> **Principle:** Downstream projects should maximize reuse of foundation's conftest fixtures. When writing new tests (in this sync or future work), prefer composing foundation fixtures over creating project-specific mocks for the same ADK interfaces. This keeps the test infrastructure aligned and future syncs lightweight.

### Phase 3: Dependencies & Build (Mixed)

**Goal:** Review dependency and build changes. pyproject.toml needs manual merge; Dockerfile and docker-compose.yml may be safe to sync directly or need manual review.

**Review order:**
1. `pyproject.toml` — **Always manual review** (has project-specific deps). Open IDE diff.
2. `Dockerfile` — Often safe to edit directly (version bumps). Open IDE diff.
3. `docker-compose.yml` — Likely has project customizations (additive merge). Open IDE diff.
4. `.env.example` — May have new variables (manual merge to preserve project-specific vars). Open IDE diff.

**For each file:** Open IDE diff and **STOP** with options:
- **Skip** — No changes needed
- **Apply edits** — Make targeted edits preserving project-specific content
- **Show foundation version** — `git show foundation-tags/$VERSION:<file>` for full file context

> **IMPORTANT:** If pyproject.toml was modified, run `uv lock` immediately. Never sync `uv.lock` directly.

### Phase 4: Infrastructure (Checkout & Restore)

**Goal:** Sync Terraform configurations. Use bulk checkout — downstream-specific files are not deleted because `git checkout` from a ref that doesn't have those files simply leaves them untouched.

**Default approach: Checkout entire directory, then unstage.** This is safe because `git checkout <ref> -- <path>` only writes files that exist in the ref — it never deletes files that are only in the working tree (downstream-specific files are preserved).

```bash
# Sync and unstage (changes go to working tree)
git checkout foundation-tags/$VERSION -- terraform/bootstrap/
git restore --staged terraform/bootstrap/

git checkout foundation-tags/$VERSION -- terraform/main/
git restore --staged terraform/main/
```

**After each checkout, verify non-destructive:**
1. Confirm downstream-specific files still exist: `ls terraform/main/<project-specific>.tf`
2. Check no downstream files were modified: `git diff -- terraform/main/<project-specific>.tf` (should be empty)
3. Show diff stats: `git diff --stat -- terraform/`

**STOP** to confirm with user before proceeding.

### Phase 5: CI/CD (Checkout & Restore)

**Goal:** Sync GitHub Actions workflows.

Safe to bulk checkout — downstream-only workflow files are preserved.

```bash
git checkout foundation-tags/$VERSION -- .github/workflows/
git restore --staged .github/workflows/
```

**After checkout, verify and clean up:**
1. Remove any foundation-only workflows not needed downstream (e.g., `deploy-docs.yml` if MkDocs is not used)
2. Show diff stats: `git diff --stat -- .github/workflows/`

**STOP** for confirmation.

### Phase 6: Configuration & Project Files

**Goal:** Review miscellaneous configuration files.

**Review order:**
1. `.gitignore` / `.dockerignore` — Check diff, usually no changes
2. `mkdocs.yml` / `notebooks/` — Skip if not used in downstream
3. `AGENTS.md` / `CLAUDE.md` — Has project-specific patterns, skip (updated separately)

For each: check if diff exists, skip if empty, **STOP** if non-empty.

### Phase 7: Documentation (Checkout & Restore)

**Goal:** Sync documentation guides.

Safe to bulk checkout — downstream-only docs are preserved.

```bash
git checkout foundation-tags/$VERSION -- docs/
git restore --staged docs/
```

**After checkout, verify non-destructive:**
1. Confirm downstream-specific docs still exist: `ls docs/<project-specific>.md`
2. Show diff stats: `git diff --stat -- docs/`

**STOP** for confirmation.

### Phase 8: Wrap-up

1. **Run full quality suite and fix any failures:**
   ```bash
   uv run ruff format && uv run ruff check --fix && uv run mypy && uv run pytest --cov --cov-report=term-missing
   ```
   Common failures after a sync:
   - Test assertions referencing renamed fields/env vars — update test expectations
   - Missing test coverage for new code — add tests (check foundation's test files for reference)
   - Import errors from renamed constants — update imports

2. **Summary:** List all sync decisions by phase:
   - Files edited (manual adaptation from foundation patterns)
   - Directories synced (checked out from foundation)
   - Files skipped
   - Files removed (foundation-only, not needed downstream)

3. **Reminders:**
   - "Run full quality suite one final time to confirm"
   - "Push and create PR when ready"

4. **Follow-up items** from "Note for later" decisions in Phases 1-2

## Recovering from Mistakes

If the user accidentally syncs a file they shouldn't have:

```bash
# Restore from HEAD (before any commits on the sync branch)
git checkout HEAD -- <file>
```

If changes were already committed:

```bash
git checkout HEAD~1 -- <file>
git commit --amend
```

## Error Handling

### No Foundation Remote
```
The 'foundation' remote is not configured.

To set it up:
  git remote add foundation <template-repo-url>

What is the URL of your agent-foundation template repository?
```
**STOP** and wait for user to provide URL.

### No Changes for Version
If `git diff --stat` shows no changes for a phase, report it and move to next phase automatically.

### Merge Conflicts
If `git checkout` produces conflicts:
1. Show conflicted files with `git status`
2. **STOP** — let user resolve manually or with merge tool
3. After resolution: `git add <files> && git commit`
