# TradingAgents — Agent Guide

Multi-agent LLM trading framework. LangGraph orchestrates analyst → researcher debate → trader → risk → portfolio-manager agents to produce a trade decision for a ticker/date.

## Runs / entrypoints

- **Interactive CLI** (the main product): console command `tradingagents` (equivalently `python -m cli.main`). Run from the project root. It drops into a questionary/typer picker for ticker, date, analysts, provider, model, output language. The `analyze` subcommand is the same flow: `tradingagents analyze [--checkpoint] [--clear-checkpoints]`.
- **Single run example**: `python main.py` (hardcoded NVDA analysis).
- **Web UI**: `pip install -r requirements-web.txt` then `uvicorn web.app:app --host 0.0.0.0 --port 8000`. SSE-based; frontend embedded in `web/app.py`.

## Venv / Python

- On Windows the `.venv` was originally created by `uv` and may point at a deleted managed interpreter (`No Python at ...uv\python...`). Recreate with system Python: delete `.venv`, then `python -m venv .venv` (system python is `C:\Users\serge\AppData\Local\Programs\Python\Python313\python.exe`), then `pip install -e .` from the repo root.
- Install editable: `pip install -e .` (installs the `tradingagents` console script from `cli.main:app`).

## Tests

- pytest only. No lint/typecheck/make/CI config exists in the repo.
- Run: `pytest` (or `pytest tests/`). `tests/conftest.py` auto-injects dummy values for all `*_API_KEY` env vars so unit tests don't hang/error without real keys.

## Config / LLM providers

- All config lives in `tradingagents/default_config.py` (`DEFAULT_CONFIG`). Key keys: `llm_provider`, `deep_think_llm`, `quick_think_llm`, `backend_url`, `data_vendors`, `tool_vendors`, `max_debate_rounds`, `max_risk_discuss_rounds`, `output_language`, `checkpoint_enabled`.
- LLM clients are created via `tradingagents/llm_clients/factory.py`. OpenAI-compatible providers (`openai`, `xai`, `deepseek`, `qwen`, `glm`, `ollama`, `openrouter`) all route through `OpenAIClient` in `llm_clients/openai_client.py`. `backend_url` overrides a provider default. Only native `openai` uses the Responses API; all other compatible providers use Chat Completions.
- Data vendors default to `yfinance` (no API key needed). Alpha Vantage requires `ALPHA_VANTAGE_API_KEY`.
- Set provider keys in `.env` (copied from `.env.example`). `main.py` and the CLI call `load_dotenv()`.

## Local working-tree gotchas

- The working tree currently has **uncommitted local changes** (see `git status` / `git diff`) that hardcode a custom local endpoint: `main.py` sets `llm_provider="ollama"`, `backend_url="http://localhost:20128/v1"`, models `auto/best-free`; `openai_client.py` changed the ollama default URL to `localhost:20128/v1` and bakes in a **secret API key** (`sk-36a78aaa...`). Do not commit that key — it is a local dev setup, not repo baseline.
- The OpenAI-compatible model catalog (`llm_clients/model_catalog.py`) has an entry `auto/best-free` added for the local endpoint; the endpoint's real model ID is `auto/best-free` (not `omnicode-local/...`). When targeting a custom endpoint, verify the exact model ID against `GET /v1/models`.

## Structure

- `tradingagents/agents/` — agent factories (`analysts/`, `researchers/`, `risk_mgmt/`, `managers/`, `trader/`, `utils/`). Expose new agents via `__all__` in `tradingagents/agents/__init__.py`.
- `tradingagents/dataflows/` — data-access layer (yfinance / AlphaVantage).
- `tradingagents/graph/` — LangGraph orchestration. `trading_graph.py` builds clients/tools and compiles the graph; `setup.py` wires nodes/edges; `tradingagents/agents/utils/agent_utils.py` holds the abstract tool functions registered as tool nodes.
- `cli/` — interactive CLI (Typer + questionary + rich). `web/` — FastAPI UI (see `web/AGENTS.md`).
- Run output persists to `~/.tradingagents/` (logs, cache, memory log).
