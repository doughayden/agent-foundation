# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Reusable CI/CD workflow pattern with three workflows: `ci-cd.yml` (orchestrator), `docker-build.yml` (multi-arch builds), `terraform-plan-apply.yml` (infrastructure deployment)
- Automatic CI/CD workflow trigger on version tag push (builds Docker images for `v*` tags)
- Smart image tagging strategy: PRs tagged as `pr-{number}-{sha}`, main branch tagged as `{sha}`, `latest`, and `{version}` (if git tag exists)
- PR automation with Terraform plan posted as comment on pull requests
- Workspace-based Terraform deployment supporting environment isolation (default/dev/stage/prod)
- GCS bucket for main module's remote state created by bootstrap module
- Vertex AI Reasoning Engine provisioning in main Terraform module for session/memory persistence
- GCS bucket for artifact storage in main Terraform module
- Docker image recycling pattern with nullable `docker_image` variable for infrastructure-only updates
- `docs/cicd-setup.md` documenting complete CI/CD workflow automation
- `docs/terraform-infrastructure.md` documenting bootstrap and main module architecture
- `docs/IMPLEMENTATION_PLAN.md` providing detailed implementation guide
- `docs/production-environment-strategy.md` for future multi-environment planning

### Changed
- Changed default Terraform workspace from `sandbox` to `default` in CI/CD workflows to use Terraform's built-in default workspace while maintaining extensibility for multi-environment deployments (dev/stage/prod)
- Reorganized `.env.example` with purpose-based grouping (Required, GitHub CI/CD, Optional) and corrected variable names
- Bootstrap module now creates GCS bucket for main module's remote state and adds storage.objectUser role for state bucket access
- Main module now uses remote state in GCS (bucket created by bootstrap) with workspace isolation
- Cloud Run deployment now integrates with Vertex AI Reasoning Engine via `AGENT_ENGINE` environment variable

### Removed
- `docs/github-docker-setup.md` (replaced by comprehensive cicd-setup.md)
- `.github/workflows/docker-build-push.yml` (superseded by reusable workflow pattern)
- `docs/IMPLEMENTATION_PLAN.md` (historical planning document, core implementation complete, architecture decisions preserved in terraform-infrastructure.md and cicd-setup.md)

### Fixed
- Documented IAM bucket access limitation in artifact storage bucket variable (project-level storage roles only work within same GCP project, cross-project access requires additional configuration)
- Cloud Run startup probe configuration now uses HTTP health checks with resilient retry strategy (5 attempts over 120 seconds) to handle container initialization delays

### Documentation
- Added inline comment justifying `roles/iam.serviceAccountUser` role requirement for Cloud Run service account attachment during deployment
- Added "Terraform Variable Overrides" section in terraform-infrastructure.md documenting GitHub Actions Variables pattern
- Added "IAM and Permissions Model" section in terraform-infrastructure.md documenting project-level IAM assumptions and cross-project limitations
- Documented `coalesce()` usage for empty string vs null handling in Terraform variables

## [0.3.0] - 2025-11-20

### Added
- CODEOWNERS file with fresh template replacement during init
- Init script now updates GitHub Actions badge URLs to point to new repository
- Init script now resets version to 0.1.0 in pyproject.toml
- Terraform infrastructure-as-code for GCP and GitHub configuration
- `terraform/bootstrap/` module for initial infrastructure (Workload Identity Federation, Artifact Registry, Reasoning Engine)
- `terraform/main/` module for Cloud Run deployment
- Automated GitHub Actions Variables creation via Terraform
- Artifact Registry cleanup policies (age-based deletion with version count protection and buildcache exemption)
- Required Terraform configuration entries in `.env.example` (AGENT_NAME, GITHUB_REPO_NAME, GITHUB_REPO_OWNER)

### Changed
- Init script now removes template author from pyproject.toml (developers no longer inherit template author info)
- Refactored GitHub info parsing to use tuples directly (removed dict conversion step)
- Made `github_owner` required in TemplateConfig (parsing is all-or-nothing)
- Improved agent directory discovery in server.py with file-based path resolution (using `.resolve()` for absolute paths and symlink resolution) and environment variable override
- GitHub Actions workflows now use Variables instead of Secrets for non-sensitive identifiers (GCP_PROJECT_ID, GCP_WORKLOAD_IDENTITY_PROVIDER)
- Renamed `ARTIFACT_REGISTRY_URL` to `ARTIFACT_REGISTRY_URI` for accuracy
- Simplified `AGENT_ENGINE_URI` to `AGENT_ENGINE` (URI prefix `agentengine://` now added in code)
- Server now defaults to `127.0.0.1` instead of `localhost` for explicit IPv4 binding
- Dockerfile now explicitly sets `PORT=8000` environment variable for consistency
- `RELOAD_AGENTS` environment variable added for optional agent hot reloading (defaults to false)

## [0.2.0] - 2025-11-17

### Added
- Template initialization script (`init_template.py`) with dry-run mode.
- Init script audit logs (`init_template_results.md`, `init_template_dry_run.md`) for change tracking
- Template setup documentation in README.md and docs/development.md
- InstructionProvider pattern for dynamic instruction generation (enables current dates, session-aware customization)
- MockReadonlyContext fixture in conftest.py for InstructionProvider testing
- Comprehensive prompt function tests (test_prompt.py, 13 tests)
- Integration tests for component wiring (test_integration.py, 5 tests)
- InstructionProvider pattern documentation in CLAUDE.md

### Changed
- Restructured package from nested `agent/` directory to flat structure (`agent.py`, `callbacks.py`, `tools.py`, `prompt.py` at root)
- Updated `global_instruction` to use InstructionProvider callable pattern instead of static string
- Sorted `LlmAgent` parameters in agent.py to match ADK field order
- Updated coverage exclusions in pyproject.toml (removed prompt.py, updated paths to flat structure)
- Updated test imports after package restructure (all existing tests passing)
- Docker Compose container name to `adk-docker-uv-local`
- Health endpoint response from `{"status": "healthy"}` to `{"status": "ok"}`
- Simplified development.md with project-specific examples
- Moved project structure documentation from README.md to development.md only

## [0.1.0] - 2025-11-12

### Added
- Google ADK agent with Gemini model integration and FastAPI server
- Dual authentication: Gemini Developer API or Vertex AI
- Agent lifecycle callbacks for logging and memory persistence (no short-circuits, all return None)
- Comprehensive unit tests with 100% coverage
- Environment variable parsing utility for safe JSON list handling with validation and fallback
- Multi-stage Docker build with uv optimization (~200MB runtime image, 5-10s rebuilds)
- Docker Compose with hot reloading (instant sync for code changes)
- Code quality tooling: ruff, mypy (strict), pytest (100% coverage)
- GitHub Actions workflows for quality checks and Docker builds
- Comprehensive documentation (README, development guides, Docker strategy, CLAUDE.md)
- Environment-based configuration with optional Agent Engine and GCS integration
- `.vscode/settings.json` to configure Pylance (excludes tests from type checking)

### Configuration
- Type checking excludes tests (standard pytest pattern): mypy checks only production code
- Ruff excludes notebooks from linting
- Notebooks for Agent Engine creation

[Unreleased]: https://github.com/doughayden/adk-docker-uv/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/doughayden/adk-docker-uv/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/doughayden/adk-docker-uv/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/doughayden/adk-docker-uv/releases/tag/v0.1.0
