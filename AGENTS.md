# Repository Guidelines

## Project Structure & Module Organization
WeFinance is a Streamlit-driven copilot split into lightweight domains. `app.py` wires shared layout and routing, while `pages/` holds user-facing flows (`bill_upload.py`, `advisor_chat.py`, `investment_recs.py`, `spending_insights.py`). Back-end logic lives in `modules/` (analysis pipelines, chat state) and `services/` (OCR, LangChain agent, recommendations, structuring). Persistent helpers sit in `utils/` (i18n, session). Assets, sample bills, locale JSON, and lightweight models reside under `assets/`, `data/`, `locales/`, and `models/` respectively, with longer-form docs in `docs/`. Tests mirror the code they protect inside `tests/`.

## Build, Test, and Development Commands
- `chmod +x setup_conda_env.sh && ./setup_conda_env.sh` — one-command Conda bootstrap.
- `conda env create -f environment.yml` (or `pip install -r requirements.txt`) — manual setup.
- `streamlit run app.py` — launch the UI at `http://localhost:8501`.
- `pytest tests` — run unit + integration suites.
- `pytest --cov=modules --cov=services --cov-report=term-missing` — confirm coverage on core layers.
- `black .` and `ruff check .` — format and lint before a PR.

## Coding Style & Naming Conventions
Follow PEP8 with 4-space indentation, type hints on public functions, and concise module docstrings. Use `snake_case` for modules, files, functions, and variables; reserve `CamelCase` for classes and `UPPER_SNAKE_CASE` for constants. Add bilingual comments only when a UI decision might confuse users. Prefer dependency injection over globals in `modules/`, and keep `services/` stateless so tests can patch them easily.

## Testing Guidelines
Unit tests live alongside their target (`tests/test_<module>.py`) and should mock external APIs (OCR, LLM). `tests/test_integration.py` exercises the upload → OCR → structuring → chat loop; update it whenever UX flows change. New work must add or adjust tests to cover both success and failure paths and keep coverage reports free of `term-missing` gaps.

## Commit & Pull Request Guidelines
Commits follow Conventional Commits (`fix:`, `ui:`, `docs:`, `chore:`) as seen in recent history; keep messages imperative with a brief English subject (Chinese suffix optional). Each PR should include a summary, linked issue or task ID, screenshots/GIFs for UI-visible work, and notes on environment deltas. Block PRs until lint, type checks, and tests pass locally.

## Security & Configuration Tips
Copy `.env.example` to `.env`, fill `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and never commit secrets. Use provider aliases (`LLM_PROVIDER=openai`) as expected by `services/langchain_agent.py`. Leave PaddleOCR downloads in their default cache (not in Git) and rotate keys before sharing demo builds or logs.
