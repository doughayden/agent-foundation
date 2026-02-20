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

Sync files in stages (see [Common Patterns](#common-patterns) for detailed examples)
```bash
# Compare foundation vs current HEAD
git diff --stat foundation-tags/$VERSION -- . ':!src/' ':!tests/'

# Stage foundation files - review with git status, edit staged files before commit
git checkout foundation-tags/$VERSION -- docs/
git commit -m "docs: sync with $VERSION"

git checkout foundation-tags/$VERSION -- .github/workflows/
git commit -m "ci: sync workflows from $VERSION"

git checkout foundation-tags/$VERSION -- terraform/
git commit -m "infra: sync terraform from $VERSION"
```

Resolve conflicts if needed
```bash
git status
git mergetool
git add <resolved-files>
git commit --amend  # Amend most recent sync commit with resolved conflicts
```

Restore custom files if needed
```bash
git checkout HEAD~1 -- docs/custom-tools.md
git commit --amend
```

### Review

Add manual changes for heavily customized files
```bash
git diff foundation-tags/$VERSION -- README.md
# Manually edit README.md to incorporate improvements
git add README.md
git commit -m "docs: incorporate upstream README improvements from $VERSION"
```

Verify sync (customize ignore patterns for expected diffs)
```bash
git diff --stat foundation-tags/$VERSION -- . ':!src/' ':!tests/' ':!README.md'
```

### Test & Merge

Test thoroughly
```bash
uv run ruff format && uv run ruff check --fix && uv run mypy
uv run pytest --cov
docker compose up --build
terraform -chdir=terraform/bootstrap/dev plan
```

Create PR and merge
```bash
git push -u origin sync/foundation-$VERSION
gh pr create --title "Sync with foundation template $VERSION"
# Review and merge via GitHub
```

> [!TIP]
> **Advanced:** To sync unreleased changes from `foundation/main`, fetch the branch (`git fetch foundation main`) and replace `foundation-tags/$VERSION` with `foundation/main` in commands above.

## Quick Reference

Sync strategy by file type. Complete [Setup](#setup) and [Prepare](#prepare) to create a branch and set a version (e.g., `VERSION=v0.9.1`)

**Safe to sync (review staged changes for project customizations):**

> [!NOTE]
> `terraform/` may contain project-specific resource configurations. `docs/` may contain custom guides and environment variables. Always review staged changes before committing.

```bash
git checkout foundation-tags/$VERSION -- .github/workflows/
git checkout foundation-tags/$VERSION -- terraform/
git checkout foundation-tags/$VERSION -- docs/ mkdocs.yml
git checkout foundation-tags/$VERSION -- notebooks/
git checkout foundation-tags/$VERSION -- .gitignore .dockerignore
# Review: git status && git diff --cached
```

**Review and edit manually (project-specific):**

```bash
# Review diffs, manually edit files to incorporate changes
git diff foundation-tags/$VERSION -- README.md CLAUDE.md
git diff foundation-tags/$VERSION -- Dockerfile docker-compose.yml .env.example
git diff foundation-tags/$VERSION -- pyproject.toml
```

**Review upstream patterns (apply manually):**

Foundation may enhance reusable code patterns. Review diffs and selectively apply improvements:

```bash
# Review utils patterns (Pydantic validation, OpenTelemetry)
git diff foundation-tags/$VERSION -- src/agent_foundation/utils/

# Review test patterns (pytest fixtures, ADK mocks)
git diff foundation-tags/$VERSION -- tests/conftest.py
```

**Never sync (your code):**
- `src/` - Your agent implementation
- `tests/` - Your test suite
- `CHANGELOG.md` - Your version history
- `init_template.py` - Removed from your project after first use
- `LICENSE` - Your project license
- `uv.lock` - Regenerate with `uv lock` after syncing pyproject.toml

> [!WARNING]
> After syncing `pyproject.toml`, run `uv lock` to regenerate lockfile. Never sync `uv.lock` - CI uses `uv sync --locked` which fails on stale lockfile.

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

For heavily customized files (README, CLAUDE.md), manually incorporate improvements:

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
