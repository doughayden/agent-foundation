# Documentation Reorganization Migration Plan

## Status: NOT STARTED

**Last Updated:** 2026-02-16

**Philosophy:** Elegant simplicity. Clear, discoverable, actionable. Task-based over technical boundaries.

## Quick Progress Checklist

- [ ] Create new structure (empty files)
- [ ] Migrate content to new docs
  - [ ] getting-started.md
  - [ ] environment-variables.md
  - [ ] development.md
  - [ ] deployment.md
  - [ ] cicd.md
  - [ ] observability.md (copy as-is)
  - [ ] troubleshooting.md
  - [ ] template-management.md
  - [ ] docs/README.md (navigation hub)
- [ ] Update references
  - [ ] Root README.md
  - [ ] CLAUDE.md
  - [ ] GitHub workflow files (.github/)
  - [ ] Source code docstrings
- [ ] Delete old structure
  - [ ] docs/base-infra/ directory
  - [ ] Old docs/README.md
- [ ] Validate
  - [ ] All links work
  - [ ] No duplicate env var docs
  - [ ] No orphaned content
- [ ] Final commit

---

## New Structure

```
docs/
├── README.md                   ← Navigation hub ("I want to..." → links)
├── getting-started.md          ← First-time setup
├── environment-variables.md    ← ALL env vars (single source of truth)
├── development.md              ← Docker, testing, code quality
├── deployment.md               ← Terraform, multi-env, Cloud Run
├── cicd.md                     ← GitHub Actions workflows
├── observability.md            ← Traces and logs (keep as-is)
├── troubleshooting.md          ← Common issues + solutions
└── template-management.md      ← Sync patterns for downstream
```

## Content Migration Map

### getting-started.md

**Sources:**
- `base-infra/bootstrap-setup.md` (entire doc)
- `base-infra/development.md` (initial setup sections only)

**Content:**
1. Prerequisites (GCP project, gcloud auth, GitHub repo)
2. Bootstrap CI/CD (terraform/bootstrap steps)
3. First deployment (terraform/main)
4. Verify deployment (test endpoints)
5. Next steps (→ development.md, deployment.md)

**Sections to extract from development.md:**
- Prerequisites/setup only
- Reference quick commands but don't duplicate them (→ CLAUDE.md)

**Philosophy:**
- Linear flow: "Here's what you do first"
- Get from zero to deployed in one doc
- Link to deeper topics, don't duplicate them

### environment-variables.md

**Sources:** Extract env vars from ALL current docs
- `base-infra/environment-variables.md` (primary)
- `base-infra/development.md` (env var mentions)
- `base-infra/terraform-infrastructure.md` (TF_VAR_*)
- `base-infra/multi-environment-guide.md` (env var mentions)
- `base-infra/docker-compose-workflow.md` (env var mentions)
- `base-infra/dockerfile-strategy.md` (env var mentions)
- `base-infra/observability.md` (OTEL_*, TELEMETRY_*)
- `base-infra/bootstrap-setup.md` (env var mentions)

**Structure:**
1. **Required** (fail without these)
   - GOOGLE_GENAI_USE_VERTEXAI
   - GOOGLE_CLOUD_PROJECT
   - GOOGLE_CLOUD_LOCATION
   - AGENT_NAME
   - OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT
2. **Optional** (reasonable defaults)
   - LOG_LEVEL
   - SERVE_WEB_INTERFACE
   - ROOT_AGENT_MODEL
   - TELEMETRY_NAMESPACE
   - etc.
3. **CI/CD Only** (GitHub Actions)
   - TF_VAR_* variables
   - GitHub Environment Variables
4. **Reference** (where set, how used)
   - Local: docker-compose.yml, .env
   - Cloud Run: Terraform main module
   - CI/CD: GitHub Environment Variables

**Philosophy:**
- Single source of truth
- Group by usage pattern, not alphabetically
- Show where/how to set each one
- Delete all env var documentation from other files

### development.md

**Sources:**
- `base-infra/development.md` (main content, minus first-time setup)
- `base-infra/docker-compose-workflow.md` (Docker Compose patterns)
- `base-infra/dockerfile-strategy.md` (understanding the build)

**Content:**
1. Quick Start (docker compose up)
2. Code Quality (ruff, mypy, pytest)
3. Testing (pytest patterns, coverage requirements)
4. Docker Compose Deep Dive (volumes, auth, customization)
5. Dockerfile Understanding (multi-stage, caching, security)
6. Common Tasks (add dependencies, update lockfile, etc.)

**Philosophy:**
- Day-to-day workflow focus
- "I want to..." structure
- Reference CLAUDE.md for commands, explain concepts here
- Consolidate all Docker content (why two separate files?)

### deployment.md

**Sources:**
- `base-infra/terraform-infrastructure.md` (Terraform structure)
- `base-infra/multi-environment-guide.md` (entire doc)

**Content:**
1. Overview (dev-only vs production mode)
2. Multi-Environment Strategy
   - Dev-only mode (default)
   - Production mode (dev → stage → prod)
   - When to use which
3. Terraform Structure
   - Bootstrap vs main modules
   - Environment-specific configs
   - State management
4. Deployment Workflows
   - Deploy to dev (PR merge)
   - Deploy to stage (prod mode only)
   - Deploy to prod (git tag + approval)
5. Image Promotion (prod mode)
6. Runtime Configuration (TF_VAR overrides)
7. Common Operations
   - Update runtime config only
   - Infrastructure changes
   - Rollback

**Philosophy:**
- Task-based: "I want to deploy to..."
- Clear decision tree: dev-only vs prod mode
- Consolidate all deployment knowledge
- Reference environment-variables.md, don't duplicate

### cicd.md

**Sources:**
- `base-infra/cicd-setup.md` (entire doc)

**Content:**
1. Overview (workflow architecture)
2. Workflows Reference
   - ci-cd.yml (orchestrator)
   - Reusable workflows (build, plan, deploy, etc.)
3. PR Flow (build, plan, comment)
4. Merge Flow (build, deploy dev, deploy stage)
5. Tag Flow (deploy prod with approval)
6. Authentication (WIF, no SA keys)
7. Customization (adding steps, environments)
8. Debugging (logs, summaries, common issues)

**Philosophy:**
- Understand the system, then customize it
- Clear flow diagrams (PR → merge → tag)
- Reference deployment.md for environment strategy
- Troubleshooting inline where relevant

### observability.md

**Sources:**
- `base-infra/observability.md` (COPY AS-IS)

**Changes:**
- None (already well-organized and task-focused)
- Just move from base-infra/ to docs/

### troubleshooting.md

**Sources:**
- NEW (consolidate scattered troubleshooting sections)
- `base-infra/development.md` (troubleshooting sections)
- `base-infra/docker-compose-workflow.md` (common issues)
- `base-infra/multi-environment-guide.md` (gotchas)
- `base-infra/terraform-infrastructure.md` (common errors)

**Content:**
1. Local Development
   - Docker auth issues
   - Port conflicts
   - Volume sync problems
2. CI/CD
   - Build failures
   - Terraform errors
   - Deployment issues
3. Cloud Run
   - Health check failures
   - Credential errors
   - Performance issues
4. General
   - Environment variable problems
   - Version conflicts

**Philosophy:**
- Problem → Solution format
- Link to detailed docs, don't duplicate
- Add new issues as discovered
- Searchable symptom descriptions

### template-management.md

**Sources:**
- NEW (document git sync patterns)

**Content:**
1. Philosophy (git-based sync vs opaque "enhance")
2. Setup (add upstream remote)
3. Common Patterns
   - Pull all doc updates
   - Pull specific file
   - Pull code changes selectively
   - Resolve conflicts
4. When to Sync
   - Quarterly? On-demand? Your choice.
5. What NOT to sync (customizations)
6. Examples (actual commands)

**Philosophy:**
- Transparent and flexible
- Git commands, not magic
- Downstream projects control their destiny
- Clear examples for common cases

### docs/README.md

**Sources:**
- NEW (navigation hub)

**Content:**
```markdown
# Documentation

Navigate by what you want to do:

## First Time Setup
- [Getting Started](getting-started.md) - Bootstrap CI/CD, first deployment
- [Environment Variables](environment-variables.md) - Complete configuration reference

## Development
- [Development](development.md) - Docker, testing, code quality
- [Deployment](deployment.md) - Terraform, multi-environment, Cloud Run

## Operations
- [CI/CD](cicd.md) - GitHub Actions workflows
- [Observability](observability.md) - Traces and logs
- [Troubleshooting](troubleshooting.md) - Common issues

## Template Management
- [Syncing Upstream Changes](template-management.md) - Pull updates from template

---

**Philosophy:** Elegant simplicity. Clear, discoverable, actionable.
```

**Philosophy:**
- Task-based navigation
- Minimal text, maximum links
- "I want to..." mental model

## Files to Delete

1. `docs/base-infra/` (entire directory)
   - bootstrap-setup.md → getting-started.md
   - cicd-setup.md → cicd.md
   - development.md → getting-started.md + development.md
   - docker-compose-workflow.md → development.md
   - dockerfile-strategy.md → development.md
   - environment-variables.md → environment-variables.md
   - multi-environment-guide.md → deployment.md
   - observability.md → observability.md
   - terraform-infrastructure.md → deployment.md
   - validating-multiplatform-builds.md → DELETED (amd64 only)

2. Old `docs/README.md` → replaced with navigation hub

## References to Update

### Root README.md
- Update "Documentation" section
- Point to docs/README.md (navigation hub)
- Remove base-infra references

### CLAUDE.md
- Update documentation references
- Change file paths
- Update "Documentation References" section

### GitHub Workflows (.github/workflows/)
- Search for markdown references in comments
- Update any documentation links

### Source Code
- Docstrings referencing docs
- Comments pointing to guides
- Grep for "base-infra" mentions

## Validation Checklist

- [ ] Every link in new docs works
- [ ] No broken cross-references
- [ ] Environment variables only in environment-variables.md
- [ ] No content orphaned (check diff)
- [ ] All old files deleted
- [ ] Root README.md updated
- [ ] CLAUDE.md updated
- [ ] GitHub workflow comments updated
- [ ] Source code references updated

## Execution Order

1. Create `docs/_planning/reorg-migration-plan.md` (this file)
2. Commit planning doc
3. Create new structure (empty files with headers)
4. Migrate content (one doc at a time, commit each)
5. Update references (root README.md, CLAUDE.md, etc.)
6. Delete old structure (final commit)
7. Validate all links and references

## Notes

- **No backward compatibility needed** (early phase)
- **Philosophy:** Elegant simplicity > comprehensive coverage
- **Task-based** > technical boundaries
- **Single source of truth** for env vars
- **Flat hierarchy** (max 1 level)
- **Consolidate** aggressively (why 2 docs when 1 works?)
- **Downstream friendly** (git sync, transparent, flexible)

---

**Next Session Recovery:**
1. Read this file
2. Check status and checklist
3. Continue where left off
