# Repository Guidelines

## Project Structure & Module Organization
Core application code lives in `app/`:
- `app/main.py`: FastAPI app lifecycle and startup/shutdown wiring.
- `app/channels/`: Slack and Telegram integrations.
- `app/agent/`: runtime, system prompt, and tool loading.
- `app/scheduler/`: proactive jobs, delivery, and runner logic.
- `app/sessions/`: SQLite-backed session persistence.

Tests are in `tests/` and mirror feature areas (`test_scheduler_jobs.py`, `test_skill_loader.py`, etc.). Runtime workspace data and prompts live in `workspace/` (`prompts/`, `skills/`, `memory/`).

## Build, Test, and Development Commands
Always run Python tooling through `uv run` (for example, `uv run pytest`, not plain `pytest`).

- `uv sync --dev`: install runtime and dev dependencies from `pyproject.toml`/`uv.lock`.
- `uv run uvicorn app.main:app --reload`: run the FastAPI service locally.
- `uv run pytest`: run the full test suite.
- `uv run pytest tests/test_scheduler_jobs.py -k cadence`: run a focused subset during development.

Use `.env.example` as the template for local configuration.

## Coding Style & Naming Conventions
Target Python `>=3.10`, 4-space indentation, and PEP 8-style formatting. Follow existing patterns:
- modules/files: `snake_case.py`
- functions/variables: `snake_case`
- classes/dataclasses: `PascalCase`
- tests: `test_*.py` and descriptive test names

Prefer type hints and `from __future__ import annotations` in new modules, matching current code.

## Testing Guidelines
Use `pytest` with `pytest-asyncio` for async behaviors (`@pytest.mark.asyncio`). Keep tests close to behavior boundaries (channels, scheduler, tools, session store) and isolate filesystem state with `tmp_path` fixtures as in `tests/conftest.py`.

There is no enforced coverage gate in config; contributors should add/extend tests for every behavior change and bug fix.

## Commit & Pull Request Guidelines
Recent commits use short, imperative subjects (for example, `Add persistent memory system (Phase 2)`). Keep commit titles concise, action-first, and scoped to one logical change.

PRs should include:
- clear summary of behavior changes
- linked issue/ticket when applicable
- test evidence (`uv run pytest` output or targeted test list)
- config or migration notes for `.env`/workspace impacts

## Security & Configuration Tips
Never commit secrets. `.env`, `client_secret*.json`, and runtime SQLite/memory artifacts are intentionally ignored. Keep real tokens only in local environment files.
