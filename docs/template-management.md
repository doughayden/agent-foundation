# Template Management

Syncing upstream changes from the template repository.

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

```bash
# 1. Check for updates
git fetch foundation 'refs/tags/*:refs/foundation-tags/*' --no-tags
git for-each-ref refs/foundation-tags --format='%(refname:short)' --sort=-version:refname | head -10

# 2. Choose version from the first step and review
git show foundation-tags/v0.9.1:CHANGELOG.md                      # See what changed
git log --oneline foundation-tags/v0.9.0..foundation-tags/v0.9.1  # Commits between versions

# 3. Create sync branch
git checkout main && git pull origin main
git checkout -b sync/foundation-v0.9.1

# 4. Sync files in stages (see Common Patterns below for detailed examples)
git diff --stat foundation-tags/v0.9.1 -- . ':!src/' ':!tests/'   # Review what to sync (customize ':!<path>' ignores)
git checkout foundation-tags/v0.9.1 -- docs/                      # Review changes with git status, edit as needed
git commit -m "docs: sync with v0.9.1"

git checkout foundation-tags/v0.9.1 -- .github/workflows/
git commit -m "ci: sync workflows from v0.9.1"

git checkout foundation-tags/v0.9.1 -- terraform/
git commit -m "infra: sync terraform from v0.9.1"

# 5. Resolve conflicts if needed
git status
git mergetool
git add <resolved-files>
git commit --amend

# 6. Restore custom files if needed
git checkout HEAD~1 -- docs/custom-tools.md
git commit --amend

# 7. Add manual changes for heavily customized files
git diff foundation-tags/v0.9.1 -- README.md
# Manually edit README.md to incorporate improvements
git add README.md
git commit -m "docs: incorporate upstream README improvements from v0.9.1"

# 8. Verify sync
git diff --stat foundation-tags/v0.9.1 -- . ':!src/' ':!tests/' ':!README.md'

# 9. Test thoroughly
uv run ruff format && uv run ruff check --fix && uv run mypy
uv run pytest --cov
docker compose up --build
terraform -chdir=terraform/bootstrap/dev plan

# 10. Create PR and merge
git push -u origin sync/foundation-v0.9.1
gh pr create --title "Sync with foundation template v0.9.1"
# Review and merge via GitHub
```

**Advanced:** Use `foundation/main` for unreleased changes. Examples above use tagged releases.

## Common Patterns

Detailed examples for step 4 (sync files) in the workflow above.

### Pull Entire Directory

**WARNING:** Overwrites ALL files in directory and deletes local files not in foundation.

```bash
# Review changes
git diff foundation-tags/v0.9.1 -- docs/

# Sync directory
git checkout foundation-tags/v0.9.1 -- docs/
git commit -m "docs: sync with foundation v0.9.1"
```

### Pull Specific File

```bash
# Review changes
git diff foundation-tags/v0.9.1 -- docs/deployment.md

# Sync file
git checkout foundation-tags/v0.9.1 -- docs/deployment.md
git commit -m "docs: sync deployment.md from v0.9.1"
```

### Pull Multiple Related Files

```bash
# Sync workflows
git checkout foundation-tags/v0.9.1 -- .github/workflows/
git commit -m "ci: sync workflows from v0.9.1"

# Sync Terraform
git checkout foundation-tags/v0.9.1 -- terraform/bootstrap/
git commit -m "infra: sync bootstrap from v0.9.1"
```

### Cherry-Pick Specific Commits

```bash
# View commits between versions
git log --oneline foundation-tags/v0.9.0..foundation-tags/v0.9.1

# Cherry-pick specific commit
git cherry-pick <commit-sha>

# Or: create patch and review
git format-patch -1 <commit-sha>
git apply --check 0001-*.patch  # Test first
git apply 0001-*.patch          # Apply if clean
git commit -m "feat: cherry-pick improvement from v0.9.1"
```

### Resolve Conflicts

```bash
# Attempt sync
git checkout foundation-tags/v0.9.1 -- docs/deployment.md

# If conflicts occur
git status  # Shows conflicted files

# Resolve manually (look for <<<< ==== >>>>) or use merge tool
git mergetool

# After resolving
git add docs/deployment.md
git commit -m "docs: merge deployment.md from v0.9.1"
```

### Restore Custom Files

If you accidentally overwrite custom files:

```bash
# Sync directory
git checkout foundation-tags/v0.9.1 -- docs/
git commit -m "docs: sync with v0.9.1"

# Restore custom file from previous commit
git checkout HEAD~1 -- docs/custom-tools.md
git commit --amend
```

### Add Manual Changes

For heavily customized files (README, CLAUDE.md), manually incorporate improvements:

```bash
# View upstream changes
git diff foundation-tags/v0.9.1 -- README.md
git show foundation-tags/v0.9.1:README.md  # Or view full file

# Manually edit your file to incorporate useful changes, then commit
git add README.md
git commit -m "docs: incorporate upstream README improvements from v0.9.1"
```

## Sync Safety

**Don't sync:**
- `src/` - Your agent code
- `tests/` - Your tests
- `uv.lock` - Always generate your own after syncing pyproject.toml
- Any file with project-specific customizations

**Safe to sync:**
- `docs/` - Documentation (if you haven't customized)
- `.github/workflows/` - CI/CD workflows (unless customized)
- `terraform/bootstrap/module/` - Shared Terraform modules

**Files with project-specific references:** `agent-foundation` -> `your-agent-name`
- `Dockerfile`, `docker-compose.yml`
- `.env.example`

**Dependencies (sync with caution):**
- `pyproject.toml` - If synced, MUST run `uv lock` to regenerate your lockfile
- **NEVER sync `uv.lock`** - Always generate your own with `uv lock` after pyproject.toml changes
- Test thoroughly after dependency updates

**When in doubt:** `git diff foundation-tags/v0.9.1 -- <file>` to review changes first.

## Troubleshooting

```bash
# Check for accidental local tag conflicts
git show-ref | grep -E 'refs/tags/(v[0-9])'

# Delete specific local foundation tags
git tag -d v0.9.0 v0.9.1

# Reset all local tags to origin (verify first: git ls-remote --tags origin)
git tag -d $(git tag -l)
git fetch origin --tags

# Reset foundation-tags namespace
git for-each-ref refs/foundation-tags --format='%(refname)' | xargs -n 1 git update-ref -d
git fetch foundation 'refs/tags/*:refs/foundation-tags/*' --no-tags
```

---

← [Back to Documentation](README.md)
