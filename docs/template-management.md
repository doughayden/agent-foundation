# Template Management

Syncing upstream changes from the template repository.

## Philosophy

This template uses **transparent git-based syncing** rather than opaque automation. You control what updates to pull and when, with full visibility into changes.

**Why git sync?**
- **Transparent:** Review changes before applying
- **Selective:** Pull only what you need
- **Flexible:** Resolve conflicts your way
- **No magic:** Standard git commands, no proprietary tools

**Contrast with agent-starter-pack:**
- agent-starter-pack: Opaque `enhance` command, trust-based updates
- agent-foundation: Git commands, full control and transparency

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

### Pull All Documentation Updates

Update all documentation to latest template version:

```bash
# Fetch latest from template
git fetch upstream main

# Check what changed in docs
git diff upstream/main -- docs/

# Pull all doc updates
git checkout upstream/main -- docs/
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

### Sync Entire docs/ Directory

Replace all documentation with template version:

```bash
# WARNING: This overwrites ALL docs with template version
git fetch upstream main
git checkout upstream/main -- docs/
git commit -m "docs: full sync with template"
```

**Use when:**
- Major template documentation overhaul
- Starting fresh with docs
- Project-specific docs are elsewhere

**Avoid when:**
- You have custom documentation mixed with template docs
- You've made project-specific changes to template docs

## When to Sync

**No strict schedule** - sync when it makes sense for your project:

- **Quarterly:** Check for infrastructure improvements, new features
- **On-demand:** When you see relevant updates in template changelog
- **Before major releases:** Ensure you have latest deployment patterns
- **When stuck:** Check if template solved the problem you're facing

**Don't sync blindly:**
- Review changes before pulling
- Test in development environment first
- Understand what each change does

## What NOT to Sync

Avoid syncing files you've customized:

**Don't sync:**
- `src/` - Your agent code
- `tests/` - Your tests
- `.env` - Your local config
- `terraform/bootstrap/*/terraform.tfvars` - Your bootstrap config
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

## Examples

### Example 1: Update CI/CD Workflows

Template added new workflow optimizations:

```bash
# Check what changed
git fetch upstream main
git diff upstream/main -- .github/workflows/

# Looks good, pull workflows
git checkout upstream/main -- .github/workflows/
git commit -m "ci: sync workflows from upstream

- Update docker-build.yml with new caching strategy
- Add retry logic to terraform-plan-apply.yml
- Update config-summary.yml output format
"

# Test in PR before merging
git push origin update-workflows
gh pr create
```

### Example 2: Update Documentation After Template Overhaul

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

# Restore any custom docs you want to keep
git checkout HEAD~1 -- docs/custom-tools.md
git commit --amend -m "docs: sync with template restructure

- Adopt new flat structure (removed base-infra/)
- Update cross-references
- Add new troubleshooting guide
- Preserve custom-tools.md
"
```

### Example 3: Selectively Update Terraform Bootstrap

Template added multi-environment support:

```bash
# Check bootstrap changes
git fetch upstream main
git diff upstream/main -- terraform/bootstrap/

# Don't want full rewrite, just cherry-pick improvements
git log --oneline HEAD..upstream/main -- terraform/bootstrap/
# Shows: "feat: add cross-project IAM for image promotion"

# Cherry-pick just that commit
git cherry-pick <commit-sha>

# Test bootstrap still works
terraform -chdir=terraform/bootstrap/dev plan

# Commit if successful
git commit
```

### Example 4: Update Just the README

Template improved README structure:

```bash
# View changes
git fetch upstream main
git diff upstream/main -- README.md

# Pull new README
git checkout upstream/main -- README.md

# Restore project-specific sections
# Edit README.md to add back your project name, description, etc.

git commit -m "docs: update README structure from upstream

- Adopt new format with clearer sections
- Preserve project-specific content
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

4. **Test thoroughly:**
   ```bash
   # Run tests
   uv run pytest --cov

   # Build Docker image
   docker compose up --build

   # Test workflows (if possible in dev)
   ```

5. **Create PR:**
   ```bash
   git push origin sync-upstream
   gh pr create --title "Sync with upstream template"
   ```

6. **Review and merge:**
   - Review changes in GitHub
   - Ensure CI passes
   - Merge when confident

## See Also

- [Development](development.md) - Local development workflow
- [Deployment](deployment.md) - Infrastructure and deployment
- [CI/CD](cicd.md) - GitHub Actions workflows
- [Getting Started](getting-started.md) - Initial setup

---

**Template Repository:** Update this line with your template repository URL after forking.
