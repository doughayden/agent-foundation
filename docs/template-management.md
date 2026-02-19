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

Add template repository as upstream remote (one-time):

```bash
# Add template as upstream
git remote add upstream https://github.com/your-org/agent-foundation.git

# Verify remotes
git remote -v
```

**Output:**
```
origin    https://github.com/your-org/your-agent.git (fetch)
origin    https://github.com/your-org/your-agent.git (push)
upstream  https://github.com/your-org/agent-foundation.git (fetch)
upstream  https://github.com/your-org/agent-foundation.git (push)
```

## Choosing a Version

**Recommended:** Sync from tagged releases for stability and reproducibility.

```bash
# List available versions
git fetch upstream --tags
git tag -l 'v*' --sort=-version:refname | head -10

# View CHANGELOG
git show v0.9.1:CHANGELOG.md

# Compare versions
git diff v0.9.0 v0.9.1 -- docs/
```

**Advanced:** Use `upstream/main` for unreleased changes. All examples below use tags - substitute `main` if needed.

## Workflow: Always Use Pull Requests

**CRITICAL:** Never commit directly to main. Always create feature branches and PRs.

```bash
# Standard workflow for any sync
git checkout main && git pull origin main     # Update local main
git checkout -b sync-upstream-v0.9.1          # Create feature branch
# ... make changes ...
git push -u origin sync-upstream-v0.9.1       # Push branch
gh pr create                                   # Create PR
# Review, approve, merge via GitHub
```

## Common Patterns

### Pull Entire Directory

Update an entire directory to latest template version.

**WARNING:** This overwrites ALL files in the directory with template versions and deletes local files not in the upstream. See [Example: Restore Custom Files](#example-restore-custom-files-after-sync) for how to recover files if needed.

```bash
# Update main and create feature branch
git checkout main && git pull origin main
git checkout -b sync-docs-v0.9.1

# Fetch tags from template
git fetch upstream --tags

# Check what changed in the directory
git diff v0.9.1 -- docs/

# Pull the directory from tagged version
git checkout v0.9.1 -- docs/

# Verify what you're about to commit
git status

# Commit the sync
git commit -m "docs: sync with template v0.9.1"

# Push and create PR
git push -u origin sync-docs-v0.9.1
gh pr create --title "docs: sync with template v0.9.1"
```

### Pull Specific File

Update a single file:

```bash
# Create feature branch
git checkout main && git pull origin main
git checkout -b sync-deployment-docs-v0.9.1

# Fetch tags
git fetch upstream --tags

# Check what changed
git diff v0.9.1 -- docs/deployment.md

# Pull specific file
git checkout v0.9.1 -- docs/deployment.md
git commit -m "docs: sync deployment.md from v0.9.1"

# Push and create PR
git push -u origin sync-deployment-docs-v0.9.1
gh pr create --title "docs: sync deployment.md from v0.9.1"
```

### Pull Multiple Related Files

Update related files as a group:

```bash
# Create feature branch
git checkout main && git pull origin main
git checkout -b sync-infrastructure-v0.9.1

# Fetch tags
git fetch upstream --tags

# Pull workflow files
git checkout v0.9.1 -- .github/workflows/
git commit -m "ci: sync workflows from v0.9.1"

# Pull Terraform bootstrap
git checkout v0.9.1 -- terraform/bootstrap/
git commit -m "infra: sync bootstrap from v0.9.1"

# Push and create PR
git push -u origin sync-infrastructure-v0.9.1
gh pr create --title "infra: sync infrastructure from v0.9.1"
```

### Pull Code Changes Selectively

Review and cherry-pick specific improvements:

```bash
# Create feature branch
git checkout main && git pull origin main
git checkout -b cherry-pick-improvements

# Fetch tags
git fetch upstream --tags

# View commits between versions
git log --oneline v0.9.0..v0.9.1

# Cherry-pick specific commit
git cherry-pick <commit-sha>

# Or: create patch and review before applying
git format-patch -1 <commit-sha>
git apply --check 0001-*.patch  # Test first
git apply 0001-*.patch          # Apply if clean
git commit -m "feat: cherry-pick improvement from v0.9.1"

# Push and create PR
git push -u origin cherry-pick-improvements
gh pr create --title "Cherry-pick improvements from v0.9.1"
```

### Check Available Updates

See what's new in template versions without pulling:

```bash
# Fetch tags
git fetch upstream --tags

# List available versions
git tag -l 'v*' --sort=-version:refname | head -10

# View CHANGELOG for a version
git show v0.9.1:CHANGELOG.md

# Compare versions
git log --oneline v0.9.0..v0.9.1

# Detailed diff between versions
git diff v0.9.0 v0.9.1

# Changes to specific directory
git diff v0.9.0 v0.9.1 -- terraform/

# File-by-file summary
git diff --stat v0.9.0 v0.9.1
```

### Resolve Conflicts

When updates conflict with customizations:

```bash
# Create feature branch
git checkout main && git pull origin main
git checkout -b resolve-sync-conflicts

# Fetch tags
git fetch upstream --tags

# Attempt pull
git checkout v0.9.1 -- docs/deployment.md

# If conflicts occur
git status  # Shows conflicted files

# Resolve manually in editor (look for <<<< ==== >>>>)
# Or: use merge tool
git mergetool

# After resolving
git add docs/deployment.md
git commit -m "docs: merge deployment.md from v0.9.1"

# Push and create PR
git push -u origin resolve-sync-conflicts
gh pr create --title "docs: merge deployment.md from v0.9.1"
```

## Sync Carefully

- Review changes before pulling
- Test in development environment first
- Understand what each change does

**Don't sync:**
- `src/` - Your agent code
- `tests/` - Your tests
- Any file with project-specific customizations

**Safe to sync:**
- `docs/` - Documentation (if you haven't customized)
- `.github/workflows/` - CI/CD workflows (unless customized)
- `terraform/bootstrap/module/` - Shared Terraform modules
- `Dockerfile`, `docker-compose.yml` - If using template versions

**When in doubt:**
- `git diff upstream/main -- <file>` to see changes
- Cherry-pick specific improvements
- Keep your customizations in separate files

## Example: Restore Custom Files After Sync

Template reorganized docs/ directory:

```bash
# Create feature branch
git checkout main && git pull origin main
git checkout -b sync-docs-restructure-v0.9.1

# Review changes
git fetch upstream --tags
git diff v0.9.1 -- docs/

# Major restructure, better to pull all docs
git checkout v0.9.1 -- docs/
git commit -m "docs: sync with template v0.9.1 restructure

- Adopt new flat structure (removed base-infra/)
- Update cross-references
- Add new troubleshooting guide
"

# Oh no! Forgot about custom-tools.md - restore it
git checkout HEAD~1 -- docs/custom-tools.md
git commit --amend -m "docs: sync with template v0.9.1 restructure

- Adopt new flat structure (removed base-infra/)
- Update cross-references
- Add new troubleshooting guide
- Preserve custom-tools.md
"

# Push and create PR
git push -u origin sync-docs-restructure-v0.9.1
gh pr create --title "docs: sync with template v0.9.1 restructure"
```

## Workflow for Major Updates

When template has significant changes (e.g., v0.9.0 → v0.9.1):

1. **Create feature branch:**
   ```bash
   git checkout main && git pull origin main
   git checkout -b sync-upstream-v0.9.1
   ```

2. **Review changes:**
   ```bash
   # Fetch tags
   git fetch upstream --tags

   # View what's new
   git log --oneline v0.9.0..v0.9.1
   git diff --stat v0.9.0 v0.9.1

   # Read CHANGELOG
   git show v0.9.1:CHANGELOG.md
   ```

3. **Pull updates incrementally:**
   ```bash
   # Docs first (safest)
   git checkout v0.9.1 -- docs/
   git commit -m "docs: sync with v0.9.1"

   # Workflows next
   git checkout v0.9.1 -- .github/workflows/
   git commit -m "ci: sync workflows from v0.9.1"

   # Infrastructure last (most critical)
   git checkout v0.9.1 -- terraform/
   git commit -m "infra: sync terraform from v0.9.1"
   ```

4. **Review and resolve:**
   ```bash
   # Check what changed
   git log --oneline -3  # Last 3 commits

   # If conflicts occurred during checkout
   git status  # Shows conflicted files

   # Resolve conflicts manually or with merge tool
   git mergetool
   git add <resolved-files>
   git commit --amend

   # Restore any custom files you need to keep
   git checkout HEAD~3 -- docs/custom-tools.md
   git commit --amend
   ```

5. **Test thoroughly:**
   ```bash
   # Run code quality checks
   uv run ruff format && uv run ruff check --fix && uv run mypy

   # Run tests
   uv run pytest --cov

   # Test server locally
   docker compose up --build  # or: uv run server

   # Verify Terraform plans (if infrastructure changed)
   terraform -chdir=terraform/bootstrap/dev plan
   ```

6. **Push and create PR:**
   ```bash
   git push -u origin sync-upstream-v0.9.1
   gh pr create --title "Sync with upstream template v0.9.1" --body "$(cat <<'EOF'
## What
Sync infrastructure, workflows, and docs from template v0.9.1.

## Why
- Keep template updates current
- Includes fixes and improvements from upstream

## How
- Sync docs/ from v0.9.1
- Sync .github/workflows/ from v0.9.1
- Sync terraform/ from v0.9.1
- Preserve custom-tools.md

## Tests
- [ ] Code quality checks pass
- [ ] Tests pass
- [ ] Server starts successfully
- [ ] Terraform plans validate
EOF
)"
   ```

7. **Review and merge:**
   - Review changes in GitHub UI
   - Ensure CI passes
   - Test in development environment
   - Merge when confident

---

← [Back to Documentation](README.md)
