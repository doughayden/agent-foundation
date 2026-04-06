# Template Management

Syncing upstream changes from the template repository.

> [!TIP]
> **First time?** Read [Setup](#setup) and [Standard Workflow](#standard-workflow).
> [Quick Reference](#quick-reference) is your copy-paste guide. 
> [Common Patterns](#common-patterns) and [Troubleshooting](#troubleshooting) are optional deep-dives.

## Philosophy

This template uses **transparent git-based syncing** rather than opaque automation. You control what updates to pull and when, with full visibility into changes.

**Why git sync?**
- **Transparent:** Review changes before applying
- **Selective:** Pull only what you need
- **Flexible:** Resolve conflicts your way
- **No magic:** Standard git commands, no proprietary tools

> [!TIP]
> The `/sync-foundation` skill (`.claude/skills/sync-foundation/SKILL.md`) provides an interactive, AI-assisted version of this workflow with phase-ordered review, IDE diffs, and per-file checkpoints.

## Setup

One-time configuration:

```bash
# Add template repository as foundation remote
git remote add foundation https://github.com/your-org/agent-foundation.git
git remote -v  # Verify

# Fetch foundation tags to refs/foundation-tags/* (avoids conflicts with local tags)
# --no-tags prevents git from also creating local copies in refs/tags/*
# See: https://git-scm.com/book/en/v2/Git-Internals-The-Refspec
git fetch foundation 'refs/tags/*:refs/foundation-tags/*' --no-tags
```

Verify foundation tags were fetched:

```bash
# List foundation tags with dates
git for-each-ref refs/foundation-tags --format='%(refname:short) | %(creatordate:short)' --sort=-creatordate
```

> [!NOTE]
> `git tag -l` only lists refs in `refs/tags/*`, not custom namespaces. We need `git for-each-ref` for `refs/foundation-tags/*`

## Standard Workflow

### Prepare

Check for updates
```bash
git fetch foundation 'refs/tags/*:refs/foundation-tags/*' --no-tags
git for-each-ref refs/foundation-tags --format='%(refname:short)' --sort=-version:refname | head -10  # Semantic version sort (latest first)
```

Choose version and set variable
```bash
# Set version for copy-paste workflow (e.g., v0.9.1)
VERSION=v0.9.1

# Review what changed
git show foundation-tags/$VERSION:CHANGELOG.md
git log --oneline foundation-tags/v0.9.0..foundation-tags/$VERSION
```

Create sync branch
```bash
git checkout main && git pull origin main
git checkout -b sync/foundation-$VERSION
```

### Sync

Work through each phase in order. See [Quick Reference](#quick-reference) for commands per phase and [Common Patterns](#common-patterns) for detailed git recipes.

| Phase | Focus | Strategy |
|-------|-------|----------|
| 1 | Test fixtures (`conftest.py`) | Sync first — everything else depends on these |
| 2 | Code + tests per module | IDE diff, adapt code and tests together |
| 3 | Bulk test sync | Wholesale replacement for unchanged test modules |
| 4 | Dependencies & build | Manual review (`pyproject.toml`, `Dockerfile`, `docker-compose.yml`) |
| 5 | Infrastructure (`terraform/`) | Bulk checkout, verify downstream files preserved |
| 6 | CI/CD (`.github/workflows/`) | Bulk checkout, remove foundation-only workflows |
| 7 | Config & project files | Per-file review (`.gitignore`, `AGENTS.md`, `README.md`) |
| 8 | Documentation (`docs/`) | Bulk checkout, verify downstream docs preserved |
| 9 | Wrap-up | Quality suite, summary, PR |

### Test & Merge

```bash
# Test thoroughly
uv run ruff format && uv run ruff check --fix && uv run mypy
uv run pytest --cov
docker compose up --build
terraform -chdir=terraform/bootstrap/dev plan

# Create PR and merge
git push -u origin sync/foundation-$VERSION
gh pr create --title "Sync with foundation template $VERSION"
# Review and merge via GitHub
```

> [!TIP]
> To sync unreleased changes from `foundation/main`, fetch the branch (`git fetch foundation main`) and replace `foundation-tags/$VERSION` with `foundation/main` in commands above.

## Quick Reference

Commands per phase. Complete [Setup](#setup) and [Prepare](#prepare) first to create a branch and set `VERSION`.

**Phase 1 — Test fixtures:**
```bash
git diff foundation-tags/$VERSION -- tests/conftest.py
# Adapt fixtures, preserving downstream-only fixtures. Replace agent_foundation with your package name.
```

**Phase 2 — Code + tests (per module):**
```bash
# Cross-package diff for src/ files: foundation ref path vs your working tree path
git diff foundation-tags/$VERSION:src/agent_foundation/utils/config.py -- src/your_agent/utils/config.py
# Plain git diff for tests/ paths
git diff foundation-tags/$VERSION -- tests/test_config.py
# Adapt both, preserving downstream-specific code. Repeat for each module.
```

**Phase 3 — Bulk test sync:**
```bash
# Check if test module only differs by package name
diff <(sed "s/agent_foundation/$DOWNSTREAM_PKG/g" <(git show foundation-tags/$VERSION:tests/<file>)) tests/<file>
# If minimal diff: checkout + sed replace. Verify no agent_foundation references remain.
```

**Phase 4 — Dependencies & build:**
```bash
git diff foundation-tags/$VERSION -- pyproject.toml
git diff foundation-tags/$VERSION -- Dockerfile docker-compose.yml .env.example
# Manual review and edit. Run uv lock after pyproject.toml changes.
```

> [!WARNING]
> After syncing `pyproject.toml`, run `uv lock` to regenerate lockfile. Never sync `uv.lock` — CI uses `uv sync --locked` which fails on stale lockfile.

**Phases 5-6 — Infrastructure & CI/CD:**
```bash
git checkout foundation-tags/$VERSION -- terraform/
git restore --staged terraform/
git checkout foundation-tags/$VERSION -- .github/workflows/
git restore --staged .github/workflows/
# Verify downstream-specific files preserved. Review with git diff --stat.
```

**Phases 7-8 — Config files & documentation:**
```bash
# Per-file review for config
git diff foundation-tags/$VERSION -- .gitignore .dockerignore README.md AGENTS.md
# Bulk checkout for docs
git checkout foundation-tags/$VERSION -- docs/
git restore --staged docs/
```

**Never bulk sync:**
- `src/` — Your agent implementation (adapt manually in Phase 2)
- `tests/` — Your test suite (sync fixtures in Phase 1, adapt per-module in Phase 2, bulk sync eligible modules in Phase 3)
- `CHANGELOG.md` — Your version history
- `init_template.py` — Removed from your project after first use
- `LICENSE` — Your project license
- `uv.lock` — Regenerate with `uv lock` after syncing pyproject.toml

## Common Patterns

Detailed examples for the Standard Workflow [Sync](#sync) and [Review](#review) phases.

### Pull Entire Directory

> [!WARNING]
> Stages all files from foundation version. Overwrites local versions of tracked files in this directory. Untracked local files are not affected. Review with `git status` before committing.

```bash
# Review changes (compares foundation vs current HEAD)
git diff foundation-tags/$VERSION -- docs/

# Sync directory
git checkout foundation-tags/$VERSION -- docs/
git commit -m "docs: sync with foundation $VERSION"
```

### Pull Specific File

```bash
# Review changes
git diff foundation-tags/$VERSION -- docs/deployment.md

# Sync file
git checkout foundation-tags/$VERSION -- docs/deployment.md
git commit -m "docs: sync deployment.md from $VERSION"
```

### Sync a File at a Different Local Path

`git checkout` requires the same path in both the source and destination. When the foundation uses a different package directory name (e.g., `agent_foundation/` vs. `your_agent/`), use `git show` to redirect the content instead:

```bash
# Review the diff across different paths
git diff foundation-tags/$VERSION:src/agent_foundation/utils/observability.py -- src/your_agent/utils/observability.py

# Write the foundation version to your local path
git show foundation-tags/$VERSION:src/agent_foundation/utils/observability.py > src/your_agent/utils/observability.py
git commit -m "chore: sync observability.py from foundation $VERSION"
```

### Pull Multiple Related Files

```bash
# Sync workflows
git checkout foundation-tags/$VERSION -- .github/workflows/
git commit -m "ci: sync workflows from $VERSION"

# Sync Terraform
git checkout foundation-tags/$VERSION -- terraform/bootstrap/
git commit -m "infra: sync bootstrap from $VERSION"
```

### Cherry-Pick Specific Commits

```bash
# View commits between versions (adjust range as needed)
git log --oneline foundation-tags/v0.9.0..foundation-tags/$VERSION

# Cherry-pick specific commit
git cherry-pick <commit-sha>

# Or: create patch and review
git format-patch -1 <commit-sha>
git apply --check 0001-*.patch  # Test first
git apply 0001-*.patch          # Apply if clean
git commit -m "feat: cherry-pick improvement from $VERSION"
```

### Resolve Conflicts

```bash
# Attempt sync
git checkout foundation-tags/$VERSION -- docs/deployment.md

# If conflicts occur
git status  # Shows conflicted files

# Resolve manually (look for <<<< ==== >>>>) or use merge tool
git mergetool

# After resolving
git add docs/deployment.md
git commit -m "docs: merge deployment.md from $VERSION"
```

### Restore Custom Files

If you accidentally overwrite custom files:

```bash
# Sync directory
git checkout foundation-tags/$VERSION -- docs/
git commit -m "docs: sync with $VERSION"

# Restore custom file from previous commit
git checkout HEAD~1 -- docs/custom-tools.md
git commit --amend
```

### Add Manual Changes

For heavily customized files (README, AGENTS.md), manually incorporate improvements:

```bash
# View upstream changes
git diff foundation-tags/$VERSION -- README.md
git show foundation-tags/$VERSION:README.md  # Or view full file

# Manually edit your file to incorporate useful changes, then commit
git add README.md
git commit -m "docs: incorporate upstream README improvements from $VERSION"
```

## Troubleshooting

```bash
# Check for accidental local tag conflicts
git show-ref | grep -E 'refs/tags/(v[0-9])'

# Delete specific local foundation tags (safe - only affects local refs)
git tag -d v0.9.0 v0.9.1
```

> [!CAUTION]
> The following commands delete ALL local tags. Verify remote state before proceeding.

```bash
# Reset all local tags to origin
git ls-remote --tags origin  # Verify what you'll restore
git tag -d $(git tag -l)     # Delete all local tags
git fetch origin --tags      # Restore from remote
```

```bash
# Reset foundation-tags namespace (safe - only affects local refs)
git for-each-ref refs/foundation-tags --format='%(refname)' | xargs -n 1 git update-ref -d
git fetch foundation 'refs/tags/*:refs/foundation-tags/*' --no-tags
```

---

← [Back to Documentation](README.md)
