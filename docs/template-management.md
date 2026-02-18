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

## Common Patterns

### Pull Entire Directory

Update an entire directory to latest template version:

**WARNING:** This overwrites ALL files in the directory with template versions and deletes local files not in the upstream. See [Example: Restore Custom Files](#example-restore-custom-files-after-sync) for how to recover files if needed.

```bash
# Fetch latest from template
git fetch upstream main

# Check what changed in the directory
git diff upstream/main -- docs/

# Pull the directory
git checkout upstream/main -- docs/

# Verify what you're about to commit
git status

# Commit the sync
git commit -m "docs: sync with template upstream"
```

### Pull Specific File

Update a single file:

```bash
# Fetch latest
git fetch upstream main

# Check what changed
git diff upstream/main -- docs/deployment.md

# Pull specific file
git checkout upstream/main -- docs/deployment.md
git commit -m "docs: sync deployment.md from upstream"
```

### Pull Multiple Related Files

Update related files as a group:

```bash
# Pull workflow files
git fetch upstream main
git checkout upstream/main -- .github/workflows/
git commit -m "ci: sync workflows from upstream"

# Pull Terraform bootstrap
git checkout upstream/main -- terraform/bootstrap/
git commit -m "infra: sync bootstrap from upstream"
```

### Pull Code Changes Selectively

Review and cherry-pick code improvements:

```bash
# Fetch latest
git fetch upstream main

# View commits
git log --oneline HEAD..upstream/main

# Cherry-pick specific commit
git cherry-pick <commit-sha>

# Or: create patch and review before applying
git format-patch -1 <commit-sha>
git apply --check 0001-*.patch  # Test first
git apply 0001-*.patch          # Apply if clean
```

### Check Available Updates

See what's new in template without pulling:

```bash
# Fetch latest
git fetch upstream main

# Summary of changes
git log --oneline --graph HEAD..upstream/main

# Detailed diff
git diff upstream/main

# Changes to specific directory
git diff upstream/main -- terraform/

# File-by-file summary
git diff --stat upstream/main
```

### Resolve Conflicts

When updates conflict with customizations:

```bash
# Attempt pull
git checkout upstream/main -- docs/deployment.md

# If conflicts occur
git status  # Shows conflicted files

# Resolve manually in editor (look for <<<< ==== >>>>)
# Or: use merge tool
git mergetool

# After resolving
git add docs/deployment.md
git commit -m "docs: merge deployment.md from upstream"
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
# Review changes
git fetch upstream main
git diff upstream/main -- docs/

# Major restructure, better to pull all docs
git checkout upstream/main -- docs/
git commit -m "docs: sync with template restructure

- Adopt new flat structure (removed base-infra/)
- Update cross-references
- Add new troubleshooting guide
"

# Oh no! Forgot about custom-tools.md - restore it
git checkout HEAD~1 -- docs/custom-tools.md
git commit --amend -m "docs: sync with template restructure

- Adopt new flat structure (removed base-infra/)
- Update cross-references
- Add new troubleshooting guide
- Preserve custom-tools.md
"
```

## Workflow for Major Updates

When template has significant changes:

1. **Create branch:**
   ```bash
   git checkout -b sync-upstream
   ```

2. **Review changes:**
   ```bash
   git fetch upstream main
   git log --oneline HEAD..upstream/main
   git diff --stat upstream/main
   ```

3. **Pull updates incrementally:**
   ```bash
   # Docs first (safest)
   git checkout upstream/main -- docs/
   git commit -m "docs: sync with upstream"

   # Workflows next
   git checkout upstream/main -- .github/workflows/
   git commit -m "ci: sync workflows"

   # Infrastructure last (most critical)
   git checkout upstream/main -- terraform/
   git commit -m "infra: sync terraform modules"
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
   # Run tests
   uv run pytest --cov

   # Test server locally
   docker compose up --build  # or: uv run server

   # Test workflows (if possible in dev)
   ```

6. **Create PR:**
   ```bash
   git push origin sync-upstream
   gh pr create --title "Sync with upstream template"
   ```

7. **Review and merge:**
   - Review changes in GitHub
   - Ensure CI passes
   - Merge when confident

---

← [Back to Documentation](README.md)
