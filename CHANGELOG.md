# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.9.1] - 2026-02-19

### Changed
- Upgrade google-adk from 1.21.0 to 1.25.1 with transitive deps
- Update .gitignore for google-adk v1.20.0+ storage (.adk/)

### Fixed
- Restore OpenAPI spec endpoint (GET /docs) via google-adk upgrade
- Add type narrowing for credentials (google-auth 2.48.0 compat)

## [0.9.0] - 2026-02-18

### Added
- MkDocs documentation site with Material theme and GitHub Pages deployment
- Documentation badge in README linking to GitHub Pages site
- GitHub Pages URL replacement pattern in init_template.py
- Multi-environment deployment with dual-mode operation (toggle via `production_mode` in ci-cd.yml)
  - Dev-only mode (default): Deploy to dev on merge to main
  - Production mode: Deploy dev+stage on merge, prod on git tag with approval gate
- Environment-specific bootstrap with separate Terraform roots (dev, stage, prod)
  - Each environment provisions WIF, Artifact Registry, state bucket, GitHub Environment and Variables
  - Cross-project IAM grants for secure image promotion (stage reads dev registry, prod reads stage)
- Image promotion workflow for production mode (pull-and-promote.yml)
  - Promotes images by digest between registries without rebuilding
  - Conditional deployment strategy: PR builds and plans, main deploys based on mode, tags trigger prod
- Real-time Terraform output streaming in CI/CD with `tee` and secure temp files
- Environment display in Terraform job summaries for visibility
- Optional PR deployment support with single-line workflow change for downstream repos needing immediate feedback

### Changed
- **BREAKING**: Remove app export from __init__.py to enable lazy loading pattern
  - Forces ADK to use fallback discovery pattern for improved developer experience
  - Ensures .env loads before module-level code executes
  - Integration tests updated to import from agent_foundation.agent
- **BREAKING**: Update callback signatures for ADK 1.21.0 API compatibility
- **BREAKING**: Resource naming switched from workspace-based to variable-based suffixes
  - Previous behavior used Terraform workspace (was "default") → `{agent_name}-default` resources
  - New behavior uses `environment` input variable (dev/stage/prod) → `{agent_name}-{environment}` resources
  - Existing deployments must recreate resources or manually rename to match new convention
  - Enables multi-environment deployment with production mode (dev → stage → prod workflows)
  - Dev-only mode continues single-environment deployment with `environment=dev` → `-dev` suffix
- Standardize workflow concurrency groups across CI/CD workflows
- Update terminology from "Reasoning Engine" to "Agent Engine" throughout documentation
- Reorganize documentation with task-based core guides (docs/*.md) and detailed references (docs/references/*.md)
- Adopt modern pytest patterns with class-based test organization

### Fixed
- Exclude release PRs from automated code review workflow
- Cloud Run output inconsistency from GCP API eventual consistency
- Exit code capture in Terraform plan and apply steps for proper error propagation in CI/CD workflow
- Terraform output logging to runner logs for complete visibility of plan and apply operations

## [0.8.0] - 2025-12-12

### Changed
- **BREAKING**: Move GitHub repository configuration from `.env` to `terraform/bootstrap/terraform.tfvars` for cleaner separation of infrastructure config from application runtime config
  - `GITHUB_REPO_OWNER` → `repository_owner` in terraform.tfvars
  - `GITHUB_REPO_NAME` → `repository_name` in terraform.tfvars
  - Bootstrap Terraform module now requires explicit tfvars (no .env fallback)
- **BREAKING**: Enforce deploy-first workflow by making `AGENT_ENGINE` and `ARTIFACT_SERVICE_URI` required for local development
  - Moved from optional to required deployment-created resources
  - Local development now requires completed deployment to cloud
  - Ensures users test full deployment pipeline early
- Restructure documentation to emphasize deploy-first workflow before local development
- Standardize prerequisite messaging with GitHub-style alerts across all user-facing documentation

## [0.7.0] - 2025-12-11

### Changed
- **BREAKING**: Upgrade to google-adk 1.20.0 and migrate to App and plugin pattern for improved modularity and ADK best practices
  - Agent now wrapped in `App` container with `GlobalInstructionPlugin` for dynamic instruction generation and `LoggingPlugin` for agent lifecycle logging
  - Package exports `app` instead of `root_agent` (breaking change for direct agent imports)
  - `global_instruction` moved from `LlmAgent` to `GlobalInstructionPlugin`
  - Integration tests simplified to pattern-based validation for better template customization (test app/agent wiring, not specific implementations)
- Display terraform apply results in CI/CD job summaries alongside plan results for better deployment visibility

## [0.6.0] - 2025-12-07

### Fixed
- Use PR head SHA instead of GitHub's temporary merge commit SHA for Docker image tags, improving traceability to actual commits in repository history
- Move OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT to required section in Terraform variables
- Prevent workload identity federation resource ID collisions by using GitHub repository ID instead of repository name, ensuring unique identifiers even for repositories with similar names
- Add `shell: bash {0}` to terraform plan for error output capture
- Truncate service account IDs to enforce GCP 30-character limit

### Added
- Dedicated bootstrap setup guide (`docs/bootstrap-setup.md`) with minimal commands and troubleshooting
- Comprehensive environment variables reference (`docs/environment-variables.md`) with WHEN/WHY/HOW context for each variable

### Changed
- Rename Terraform dotenv data source from `adk` to `config` in bootstrap module for clarity after project rename
- Update documentation naming consistency: replace "ADK agent" with "LLM agent", update example project IDs from `my-adk-*` to `my-agent-*`
- **BREAKING**: Rename project from `adk-docker-uv` to `agent-foundation` to better reflect production-grade infrastructure focus
  - Repository: `doughayden/adk-docker-uv` → `doughayden/agent-foundation`
  - Package: `adk_docker_uv` → `agent_foundation`
  - Docker images: `adk-docker-uv` → `agent-foundation`
  - All imports, configuration, and documentation updated
- Streamline developer onboarding: condense README from 170 to 106 lines (38% reduction), integrate template initialization into Getting Started Phase 1, remove duplication between Quickstart and Getting Started sections
- Condense development guide from 315 to 164 lines (48% reduction) with even density throughout, remove verbose code examples, combine related workflow sections
- Reorganize README Documentation section with logical grouping: Getting Started, Infrastructure and Deployment, Production Features
- Use generic placeholders (your-agent-name, your_agent_name) in documentation examples
- Update project structure tree in development.md to reflect current files and directories
- Optimize CLAUDE.md for AI consumption: 36% size reduction (440→279 lines), replace verbose prose with dense technical summaries, update outdated utils references (env_parser.py → config.py/observability.py), add branch protection warning
- Add explicit project parameters to all GCP resources in bootstrap Terraform module for clarity and reduced misconfiguration risk
- Exclude main Terraform module lockfile from version control to prevent platform-specific conflicts from local testing (CI/CD-only execution)

## [0.5.0] - 2025-11-27

### Added
- OpenTelemetry observability with trace export to Google Cloud Trace via OTLP and log export to Cloud Logging with automatic trace correlation
- Pydantic-based environment configuration (`ServerEnv` model) with type-safe validation and required field enforcement
- Comprehensive observability documentation (`docs/observability.md`) covering setup, resource attributes, and usage
- OpenTelemetry resource attributes for service identification: `service.name`, `service.namespace`, `service.version`, `service.instance.id`, and `gcp.project_id`
- Workspace-based resource naming in Terraform using `local.resource_name = "${var.agent_name}-${terraform.workspace}"` for environment-specific resources
- Automatic trace grouping by environment via `TELEMETRY_NAMESPACE` environment variable (set to workspace name in deployments)
- Billing labels (`application`, `environment`) on all GCP resources for cost tracking and organization
- UUID-based instance ID (`service.instance.id=worker-{PID}-{UUID}`) for collision-free process tracking
- Cloud Run revision tracking via `service.version` resource attribute

### Changed
- Required environment variables now include `AGENT_NAME` (service identifier) and `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` (LLM content capture control)
- Terraform resources now use workspace-based naming for environment isolation (e.g., `my-agent-dev`, `my-agent-prod`)
- Cloud Run services automatically receive `TELEMETRY_NAMESPACE = terraform.workspace` environment variable for trace grouping
- Server startup now configures OpenTelemetry before ADK initialization for proper resource attribute propagation
- Environment configuration now uses Pydantic models with factory pattern (`initialize_environment`) for validation and error handling

### Fixed
- Add `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` to Terraform bootstrap and main modules for proper deployment configuration

### Removed
- File logging system with rotating handlers (replaced with cloud-native OpenTelemetry logging)
- `src/agent_foundation/utils/env_parser.py` module (replaced with Pydantic-based configuration)
- `src/agent_foundation/utils/log_config.py` module (replaced with `observability.py`)
- `tests/test_env_parser.py` and `tests/test_logging.py` (replaced with `tests/test_config.py`)
- Log volume mount from `docker-compose.yml` (no longer needed without file logging)

## [0.4.1] - 2025-11-26

### Changed
- CI/CD workflows now use image digest (instead of tag) for Cloud Run deployments to ensure every Docker rebuild triggers a new revision deployment, even when tags are reused (e.g., base image security updates, manual rebuilds)

### Added
- "Image Digest Deployment" section in CLAUDE.md explaining digest-based deployment rationale and workflow
- "Tracing Deployed Image to Git Commit" troubleshooting section in docs/cicd-setup.md with gcloud commands to lookup digest → tags → commit SHA

## [0.4.0] - 2025-11-25

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
- Inline comment justifying `roles/iam.serviceAccountUser` role requirement for Cloud Run service account attachment during deployment
- Documentation of `coalesce()` usage for empty string vs null handling in Terraform variables
- "Terraform Variable Overrides" section in terraform-infrastructure.md documenting GitHub Actions Variables pattern
- "IAM and Permissions Model" section in terraform-infrastructure.md documenting project-level IAM assumptions and cross-project limitations

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
- Docker Compose container name adds `-local` suffix
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

[Unreleased]: https://github.com/doughayden/agent-foundation/compare/v0.9.1...HEAD
[0.9.1]: https://github.com/doughayden/agent-foundation/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/doughayden/agent-foundation/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/doughayden/agent-foundation/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/doughayden/agent-foundation/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/doughayden/agent-foundation/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/doughayden/agent-foundation/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/doughayden/agent-foundation/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/doughayden/agent-foundation/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/doughayden/agent-foundation/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/doughayden/agent-foundation/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/doughayden/agent-foundation/releases/tag/v0.1.0
