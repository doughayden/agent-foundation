# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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
