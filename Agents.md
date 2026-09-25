# How to run CLI terminal - venv activation



 & q:/github/sshilko/TradingAgents/.venv/Scripts/Activate.ps1

 tradingagents

# TradingAgents — Agent Guide

Multi-agent LLM trading framework. LangGraph orchestrates analyst → researcher debate → trader → risk → portfolio-manager agents to produce a trade decision for a ticker/date.

## Runs / entrypoints

- **Interactive CLI** (the main product): console command `tradingagents` (equivalently `python -m cli.main`). Run from the project root. It drops into a questionary/typer picker for ticker, date, analysts, provider, model, output language. The `analyze` subcommand is the same flow: `tradingagents analyze [--checkpoint] [--clear-checkpoints]`.
- **Single run example**: `python main.py` (hardcoded NVDA analysis).
- **Web UI**: `pip install -r requirements-web.txt` then `uvicorn web.app:app --host 0.0.0.0 --port 8000`. SSE-based; frontend embedded in `web/app.py`.
- **Scrolling the report while a run is live**: the "Current Report" panel scrolls with Up/Down (one line), Page Up/Page Down (one window), and Home/End (first/last line). Plain characters are ignored, so a stray key press neither scrolls nor quits. The panel title shows the visible range and which direction has more text. `cli/report_scroller.py` holds the renderable, the offset, and the key reader; see "Report panel scrolling" below.

## Venv / Python

- On Windows the `.venv` was originally created by `uv` and may point at a deleted managed interpreter (`No Python at ...uv\python...`). Recreate with system Python: delete `.venv`, then `python -m venv .venv` (system python is `C:\Users\serge\AppData\Local\Programs\Python\Python313\python.exe`), then `pip install -e .` from the repo root.
- Install editable: `pip install -e .` (installs the `tradingagents` console script from `cli.main:app`).

## Tests

- pytest only. No lint/typecheck/make/CI config exists in the repo.
- Run: `pytest` (or `pytest tests/`). `tests/conftest.py` auto-injects dummy values for all `*_API_KEY` env vars so unit tests don't hang/error without real keys.

## Config / LLM providers

- All config lives in `tradingagents/default_config.py` (`DEFAULT_CONFIG`). Key keys: `llm_provider`, `deep_think_llm`, `quick_think_llm`, `backend_url`, `data_vendors`, `tool_vendors`, `max_debate_rounds`, `max_risk_discuss_rounds`, `output_language`, `checkpoint_enabled`.
- `llm_provider`, `deep_think_llm` and `quick_think_llm` resolve as env `LLM_PROVIDER` / `LLM_MODEL` → the `default_provider` and `"default": true` marks in `models.json` → the built-in `ollama` / `auto/best` fallback. They are read at import time.
- LLM clients are created via `tradingagents/llm_clients/factory.py`. OpenAI-compatible providers (`openai`, `xai`, `deepseek`, `qwen`, `glm`, `ollama`, `openrouter`) all route through `OpenAIClient` in `llm_clients/openai_client.py`. Built-in provider base URLs and API-key env vars live in `_PROVIDER_CONFIG`; `backend_url` overrides a provider default. Only native `openai` uses the Responses API; all other compatible providers use Chat Completions.
- Data vendors default to `yfinance` (no API key needed). Alpha Vantage requires `ALPHA_VANTAGE_API_KEY`.
- Set provider keys in `.env` (copied from `.env.example`). `main.py` and the CLI call `load_dotenv()`.

## models.json (user-defined providers and models)

`models.json` in the repo root holds every provider that is not built into the code. Self-hosted and LAN endpoints (Unsloth Desktop, MTPLX) and their model lists live there. **Add a provider or a model by editing that file. Do not add Python.**

- **Loader**: `tradingagents/llm_clients/external_providers.py`. It returns `ExternalProvider` records: `key`, `label`, `client`, `base_url`, `api_key_env`, `open_models`, `allow_custom_model`, `models`, `defaults`.
- **Consumers**: `model_catalog.py` (merges into `MODEL_OPTIONS`, the only catalog the CLI and validators read), `factory.py` (client kind per provider), `openai_client.py` (`_provider_endpoint`), `validators.py` (`open_models` providers skip the known-model check), `cli/utils.py` and `web/config.py` (provider pickers), `default_config.py` (the default provider and model). When you add a consumer, read the loader instead of hardcoding provider names.
- **Path lookup**: `TRADINGAGENTS_MODELS_FILE` → repo root (`parents[2]` of the loader module) → `Path.cwd()`. A non-editable `pip install` needs the env var, because the file ships with the repo, not the wheel.
- **Reload**: results are cached on the file mtime, so a long-running web server picks up edits without a restart. `reload_external_providers()` drops the cache; tests use it.

File shape:

```json
{
  "default_provider": "lab-box",
  "providers": {
    "lab-box": {
      "label": "Lab Box (LAN)",
      "client": "openai",
      "base_url": "http://10.0.0.9:8000/v1",
      "api_key_env": "LAB_API_KEY",
      "open_models": true,
      "allow_custom_model": true,
      "models": {
        "quick": [["Lab 14B - fast", "lab-14b"]],
        "deep": [
          { "label": "Lab 70B - best", "id": "lab-70b", "default": true }
        ]
      }
    }
  }
}
```

| Field | Rule |
|-------|------|
| `default_provider` | Top-level, outside `providers`. Names the provider the CLI starts on. Must be a provider key in the same file; an unknown key warns and is ignored. |
| provider key | Lower-case id used as `llm_provider`. Must not clash with a built-in key. |
| `label` | Picker text. Defaults to the key. |
| `client` | One of `openai`, `anthropic`, `google`, `azure`. Defaults to `openai`. Only use a non-OpenAI client after adding that provider to `factory._client_kind`. |
| `base_url` | Endpoint URL. A `backend_url` from config still wins. Optional. |
| `api_key_env` | Env var with the bearer token; falls back to `API_KEY`. `null` sends no provider token. |
| `open_models` | `true` accepts any model name and suppresses the unknown-model warning. Use it for self-hosted servers. |
| `allow_custom_model` | `true` appends the `Custom model ID` entry to each mode, so the user can type any model ID. |
| `models` | Required. Keys are the selection modes `quick` and `deep`; a mode you omit copies the mode you supply. |
| `default` | Option field, object form only. `true` preselects that model in the picker for its mode and sets `DEFAULT_CONFIG` when no provider is chosen. |

- **Option format**: `["display text", "model-id"]` or `{"label": "display text", "id": "model-id"}`. `display`/`value`/`model` are accepted aliases for the object form. Both elements must be non-empty text; a bad option is skipped with a warning. `default: true` is read only from the object form, needs the literal `true` (`"true"` is text, not a mark), and never reorders the list. A mode with two marks warns and keeps the first. A mode copied from another mode copies its mark.
- **Precedence**: env `LLM_PROVIDER` / `LLM_MODEL` → the mark in `models.json` → the built-in fallback (`ollama` / `auto/best`). `default_config.py` resolves the provider first and looks the model up for **that** provider, so setting `LLM_PROVIDER=openai` never keeps a model marked for another provider. Both are read at import time, which is why the tests reload the module.
- **Picker wiring**: `cli/utils.py` passes `default=` to `questionary.select`. questionary raises when the default is not among the choices, so the model picker checks the marked id against the option list first; the provider picker builds the `(key, base_url)` tuple from its own choice list.
- **Failure behavior**: a missing file, broken JSON, or a bad entry never stops the app. The loader emits a `RuntimeWarning` naming the problem and the built-in catalog keeps working. Add a provider entry only after confirming the warning list is empty (`tests/test_external_providers.py::test_shipped_file_parses_without_warnings`).
- **Verify model IDs** against the endpoint's `GET /v1/models` before writing them. IDs that carry a repo prefix (Unsloth) must match exactly.
- **Tests**: `tests/test_external_providers.py` covers the loader (path lookup, merge, invalid entries, reload). `tests/test_model_validation.py` asserts the merged catalog is well formed; it derives its provider lists from the code, so it needs no edit when a provider moves.

## Report panel scrolling (terminal CLI)

Rich crops a renderable that is taller than its layout section, so a long report used to be unreadable below the fold. `cli/report_scroller.py` fixes that.

- **Why a custom renderable**: `ScrollableReport` is put in the `analysis` layout section and renders a `Panel` itself. It reads the section size from the `ConsoleOptions` Rich hands it, so the window height follows the terminal with no layout math in the code. `update_display` sets the renderable once; every `Live` refresh re-renders it, which is why a key press shows up without a layout update.
- **Offset**: `ReportScroller` holds the offset. The key thread only appends to a list (`queue_key`); the offset moves during render (`apply_pending`), so key input never races the render thread and several presses between two frames stack up in order. The offset is clamped to the content, so a shrinking report cannot leave the view past the end.
- **Key reader**: `KeyReader` reads keys on a background thread and never echoes them. Windows uses `msvcrt.kbhit`/`getch` with the 0x00/0xE0 prefix; POSIX uses `termios` cbreak (not raw) plus `select`, so Rich's output control codes still work. `is_supported()` returns False for piped stdin, and the context manager makes the run safe either way.
- **Only navigation keys count**: `decode_windows_key` and `parse_ansi_keys` return `None` for anything but Up/Down/Page Up/Page Down/Home/End. A typed letter cannot scroll or quit the run.
- **Panel chrome**: the renderable subtracts `PANEL_CHROME_WIDTH`/height` for the border and padding. Keep them in step with the `Panel` in `ScrollableReport`, or the pre-rendered lines re-wrap.
- **Tests**: `tests/test_report_scroller.py` covers key decoding, offset math, the rendered window, and the Windows read loop with a fake console.

## Local working-tree gotchas

- The working tree currently has **uncommitted local changes** (see `git status` / `git diff`) that hardcode a custom local endpoint: `main.py` sets `llm_provider="ollama"`, `backend_url="http://localhost:20128/v1"`, models `auto/best-free`; `openai_client.py` changed the ollama default URL to `localhost:20128/v1` and bakes in a **secret API key** (`sk-36a78aaa...`). Do not commit that key — it is a local dev setup, not repo baseline.
- The local endpoint serves the model id `auto/best-free` (from `.env.example` `LLM_MODEL`), while the built-in ollama catalog and `DEFAULT_CONFIG` still list `auto/best`. Verify the exact id against `GET /v1/models` before relying on either. An endpoint that is not built in belongs in `models.json`, not in `model_catalog.py`.

## Structure

- `tradingagents/agents/` — agent factories (`analysts/`, `researchers/`, `risk_mgmt/`, `managers/`, `trader/`, `utils/`). Expose new agents via `__all__` in `tradingagents/agents/__init__.py`.
- `tradingagents/dataflows/` — data-access layer (yfinance / AlphaVantage).
- `tradingagents/graph/` — LangGraph orchestration. `trading_graph.py` builds clients/tools and compiles the graph; `setup.py` wires nodes/edges; `tradingagents/agents/utils/agent_utils.py` holds the abstract tool functions registered as tool nodes.
- `cli/` — interactive CLI (Typer + questionary + rich). `web/` — FastAPI UI (see `web/AGENTS.md`).
- `tradingagents/llm_clients/` — client factory per provider, the built-in model catalog, validators, and `external_providers.py`, which loads `models.json` from the repo root. `models.json` and the loader travel together: change the catalog data in the file, and the loader code only when the file format itself changes.
- Run output persists to `~/.tradingagents/` (logs, cache, memory log).
