# TradingAgents Web Interface — Architecture Options

> **Goal:** Replace the terminal-based CLI (`cli/main.py`) with a web-based UI for running TradingAgents analysis.

---

## 1. Current Architecture Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLI (Typer + Rich)                      │
│  ┌──────────┐   ┌───────────┐   ┌──────────────────────────┐   │
│  │ Prompts  │──▶│ Config    │──▶│ TradingAgentsGraph       │   │
│  │(questionary)│ │ Builder   │   │ ┌────────────────────┐   │   │
│  └──────────┘   └───────────┘   │ │ LangGraph Workflow │   │   │
│                                 │ └────────────────────┘   │   │
│                                 │ ┌────────────────────┐   │   │
│                                 │ │ LLM Clients        │   │   │
│                                 │ └────────────────────┘   │   │
│                                 └──────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**Key entry point:** [`TradingAgentsGraph.propagate(ticker, date)`](tradingagents/graph/trading_graph.py:264) — returns `(final_state, processed_signal)`.

**CLI dependencies to abstract away:**
- `typer` — CLI framework
- `rich` — terminal UI rendering
- `questionary` — interactive prompts

---

## 2. Option Comparison Matrix

| Criteria | **A: FastAPI Backend** | **B: Streamlit App** | **C: Full-Stack (React + FastAPI)** | **D: Jupyter/Gradio** |
|---|---|---|---|---|
| **Complexity** | Medium | Low | High | Low |
| **Development Time** | 3-5 days | 1-2 days | 2-3 weeks | 1-2 days |
| **Real-time Streaming** | ✅ SSE/WebSocket | ✅ `st.empty` | ✅ Native | ✅ Gradio streaming |
| **Production Ready** | ✅ Yes | ⚠️ Limited | ✅ Yes | ⚠️ Demo-focused |
| **Mobile Friendly** | ✅ SPA | ⚠️ Responsive | ✅ SPA | ❌ Desktop |
| **Learning Curve** | Medium | Low | High | Low |
| **State Management** | Server-side sessions | Stateless/Redis | Client-side | Server-side |
| **Deployment** | Docker/uvicorn | Streamlit Cloud | Vercel + AWS | Streamlit Cloud |

---

## 3. Detailed Option Analysis

### Option A: FastAPI Backend + SSE Streaming ⭐ RECOMMENDED

**Architecture:**
```
┌──────────────┐     HTTP/SSE      ┌──────────────────────────┐
│  Any Client  │◀══════════════▶  │  FastAPI Server          │
│  (Browser/   │   Streaming      │  ┌────────────────────┐  │
│   Mobile)    │   Events         │  │ TradingAgentsGraph │  │
└──────────────┘                  │  └────────────────────┘  │
                                  │  ┌────────────────────┐  │
                                  │  │ Async Task Queue   │  │
                                  │  │ (Celery/RQ/Arq)    │  │
                                  │  └────────────────────┘  │
                                  └──────────────────────────┘
```

**Core Implementation:**

```python
# web/app.py
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import asyncio
import json

app = FastAPI(title="TradingAgents Web Interface")

# Background task for graph execution
async def run_analysis(ticker: str, date: str, config: dict, event_queue: asyncio.Queue):
    """Run TradingAgentsGraph and emit events via queue."""
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    
    graph = TradingAgentsGraph(config=config)
    
    # Emit events during graph execution
    # (requires callback integration with LangGraph)
    result = await asyncio.to_thread(graph.propagate, ticker, date)
    
    await event_queue.put({
        "type": "complete",
        "data": result
    })

@app.post("/api/analyze")
async def analyze(ticker: str, date: str, config: dict):
    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(run_analysis(ticker, date, config, queue))
    return StreamingResponse(event_generator(task, queue))
```

**Pros:**
- Clean separation of concerns
- API-first design (mobile apps, third-party integrations)
- Native SSE support for real-time updates
- Easy WebSocket integration for live chat-style updates
- Production-grade async support

**Cons:**
- Requires building frontend separately
- More boilerplate code

**Key Dependencies:**
```toml
[dependencies]
fastapi = "^0.115.0"
uvicorn = "^0.32.0"
python-multipart = "^0.0.12"
sse-starlette = "^2.2.0"
websockets = "^14.0"
```

---

### Option B: Streamlit Single-File App

**Architecture:**
```
┌──────────────────────────────────────────────────┐
│              Streamlit App                       │
│  ┌────────────┐    ┌────────────────────────┐   │
│  │ Sidebar    │    │ Main Panel             │   │
│  │ - Ticker   │    │ - Live progress        │   │
│  │ - Date     │    │ - Analyst reports      │   │
│  │ - Config   │    │ - Final decision       │   │
│  └────────────┘    └────────────────────────┘   │
│         │                                          │
│         ▼                                          │
│  TradingAgentsGraph.propagate()                   │
└──────────────────────────────────────────────────┘
```

**Core Implementation:**

```python
# web/streamlit_app.py
import streamlit as st
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

st.set_page_config(page_title="TradingAgents", layout="wide")

# Sidebar configuration
with st.sidebar:
    ticker = st.text_input("Ticker Symbol", "SPY")
    date = st.date_input("Analysis Date", format="YYYY-MM-DD")
    analysts = st.multiselect("Analysts", ["market", "social", "news", "fundamentals"])
    run_button = st.button("Run Analysis")

# Main panel
if run_button and ticker:
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Create containers for each section
    analyst_cols = st.columns(2)
    report_containers = {
        "market": analyst_cols[0].empty(),
        "sentiment": analyst_cols[1].empty(),
        "news": analyst_cols[0].empty(),
        "fundamentals": analyst_cols[1].empty(),
    }
    
    config = DEFAULT_CONFIG.copy()
    config["selected_analysts"] = analysts or ["market", "social", "news", "fundamentals"]
    
    with st.spinner("Running TradingAgents..."):
        graph = TradingAgentsGraph(config=config)
        final_state, signal = graph.propagate(ticker, date.strftime("%Y-%m-%d"))
        
        # Display results
        st.success("Analysis Complete!")
        st.markdown("### Final Trade Decision")
        st.write(final_state["final_trade_decision"])
```

**Pros:**
- Single Python file — minimal setup
- Built-in caching (`@st.cache_data`)
- Responsive layout out of the box
- No JavaScript required

**Cons:**
- Limited customization of UI components
- Full rerun on interaction (not true SPA)
- Streaming requires workarounds (`st.empty`, `st.status`)
- Not ideal for complex dashboards

**Key Dependencies:**
```toml
[dependencies]
streamlit = "^1.41.0"
pandas = "^2.2.0"
plotly = "^5.24.0"
```

---

### Option C: Full-Stack (React/Vue + FastAPI)

**Architecture:**
```
┌─────────────────┐     REST/SSE      ┌──────────────────────────┐
│  React Frontend │◀══════════════▶  │  FastAPI Backend         │
│  (Vite + TS)    │                  │  ┌────────────────────┐  │
│                 │                  │  │ TradingAgentsGraph │  │
│  - Real-time    │                  │  └────────────────────┘  │
│    updates      │                  │                          │
│  - Charts       │                  │  ┌────────────────────┐  │
│  - Config UI    │                  │  │ PostgreSQL/Redis   │  │
│                 │                  │  └────────────────────┘  │
└─────────────────┘                  └──────────────────────────┘
```

**Pros:**
- Maximum flexibility and customization
- Best user experience
- Scalable to complex dashboards
- Can add user accounts, history, portfolio tracking

**Cons:**
- Significant development effort
- Two codebases to maintain
- Build pipeline required
- Overkill for single-user tool

---

### Option D: Gradio Interface

**Architecture:**
```
┌──────────────────────────────────────────────────┐
│              Gradio App                          │
│  ┌────────────┐    ┌────────────────────────┐   │
│  │ Inputs     │    │ Outputs                │   │
│  │ - Ticker   │──▶ │ - Markdown reports     │   │
│  │ - Config   │    │ - Charts/Plots         │   │
│  └────────────┘    └────────────────────────┘   │
│         │                                          │
│         ▼                                          │
│  TradingAgentsGraph.propagate()                   │
└──────────────────────────────────────────────────┘
```

**Core Implementation:**

```python
# web/gradio_app.py
import gradio as gr
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

def run_analysis(ticker, date, analysts_json, config_json):
    import json
    analysts = json.loads(analysts_json)
    config = json.loads(config_json)
    
    graph = TradingAgentsGraph(selected_analysts=analysts, config=config)
    final_state, signal = graph.propagate(ticker, date)
    
    return (
        final_state.get("market_report", ""),
        final_state.get("sentiment_report", ""),
        final_state.get("news_report", ""),
        final_state.get("fundamentals_report", ""),
        final_state.get("final_trade_decision", ""),
        json.dumps(signal, indent=2)
    )

with gr.Blocks(title="TradingAgents") as demo:
    gr.Markdown("# TradingAgents Web Interface")
    
    with gr.Row():
        ticker_input = gr.Textbox(label="Ticker Symbol", value="SPY")
        date_input = gr.Textbox(label="Date (YYYY-MM-DD)", value="2024-01-15")
    
    analysts_input = gr.CheckboxGroup(
        label="Analysts",
        choices=["market", "social", "news", "fundamentals"],
        value=["market", "social", "news", "fundamentals"]
    )
    
    run_btn = gr.Button("Run Analysis")
    
    with gr.Tabs():
        with gr.Tab("Market Report"):
            market_output = gr.Markdown()
        with gr.Tab("Sentiment Report"):
            sentiment_output = gr.Markdown()
        with gr.Tab("News Report"):
            news_output = gr.Markdown()
        with gr.Tab("Fundamentals Report"):
            fundamentals_output = gr.Markdown()
        with gr.Tab("Final Decision"):
            decision_output = gr.Markdown()
        with gr.Tab("Signal"):
            signal_output = gr.JSON()
    
    run_btn.click(
        fn=run_analysis,
        inputs=[ticker_input, date_input, analysts_input, gr.JSON(value=DEFAULT_CONFIG)],
        outputs=[market_output, sentiment_output, news_output, 
                 fundamentals_output, decision_output, signal_output]
    )

demo.launch(server_name="0.0.0.0", server_port=7860)
```

**Pros:**
- Minimal code required
- Built-in sharing (Gradio Spaces)
- Good for ML/AI applications
- Markdown/JSON output rendering

**Cons:**
- Limited UI customization
- Not ideal for complex interactions
- Streaming support is basic

---

## 4. Recommended Implementation Plan (FastAPI Option)

### Phase 1: Backend API Layer

```
web/
├── app.py                 # FastAPI main application
├── api/
│   ├── __init__.py
│   ├── analysis.py        # POST /api/analyze endpoint
│   ├── status.py          # GET /api/status/{task_id} endpoint
│   └── config.py          # GET/POST /api/config endpoints
├── tasks/
│   ├── __init__.py
│   └── runner.py          # Background task runner
├── events/
│   ├── __init__.py
│   └── emitter.py         # SSE event emitter
└── static/
    └── index.html         # Simple frontend
```

**Key API Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/analyze` | Start new analysis |
| GET | `/api/status/{task_id}` | Get task status |
| GET | `/api/result/{task_id}` | Get final result |
| GET | `/api/events/{task_id}` | SSE stream for live updates |
| GET | `/api/config` | Get current configuration |
| POST | `/api/config` | Update configuration |
| GET | `/api/history` | Get past analyses |

### Phase 2: Frontend Components

```
frontend/
├── src/
│   ├── App.tsx
│   ├── components/
│   │   ├── AnalysisForm.tsx      # Ticker, date, analyst selection
│   │   ├── ProgressTracker.tsx   # Live progress visualization
│   │   ├── ReportCard.tsx        # Individual report display
│   │   ├── DecisionPanel.tsx     # Final trade decision
│   │   └── ConfigPanel.tsx       # LLM config, settings
│   ├── hooks/
│   │   ├── useSSE.ts             # SSE connection hook
│   │   └── useAnalysis.ts        # Analysis state management
│   └── types/
│       └── index.ts              # TypeScript types
└── package.json
```

### Phase 3: Real-time Event System

```python
# web/events/emitter.py
import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator, Dict, Any

class EventEmitter:
    """Emits SSE events for real-time frontend updates."""
    
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.events: list[Dict[str, Any]] = []
    
    def format_sse(self, data: Dict[str, Any]) -> str:
        return f"event: analysis_update\ndata: {json.dumps(data)}\n\n"
    
    async def event_generator(self) -> AsyncGenerator[str, None]:
        yield self.format_sse({
            "type": "connected",
            "task_id": self.task_id,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Wait for events from the analysis queue
        while True:
            event = await self.queue.get()
            self.events.append(event)
            yield self.format_sse(event)
```

---

## 5. Integration Points with Existing Code

### 5.1 Callback Integration for Live Updates

Modify [`TradingAgentsGraph`](tradingagents/graph/trading_graph.py:49) to accept callbacks:

```python
# Current: callbacks only for LLM/tool stats
def propagate(self, company_name, trade_date):
    ...
    for chunk in self.graph.stream(init_agent_state, **args):
        # Add callback here for SSE emission
        if self.callbacks:
            for cb in self.callbacks:
                cb.on_node_complete(chunk)
```

### 5.2 Configuration Abstraction

The [`DEFAULT_CONFIG`](tradingagents/default_config.py) can be exposed via API:

```python
# web/api/config.py
from tradingagents.default_config import DEFAULT_CONFIG

@app.get("/api/config")
async def get_config():
    # Return sanitized config (exclude API keys)
    safe_config = {k: v for k, v in DEFAULT_CONFIG.items() 
                   if "key" not in k.lower() and "token" not in k.lower()}
    return safe_config
```

### 5.3 Result Serialization

Results from [`propagate()`](tradingagents/graph/trading_graph.py:264) are already JSON-serializable:

```python
# web/api/analysis.py
@app.post("/api/analyze")
async def analyze(ticker: str, date: str, config: dict):
    graph = TradingAgentsGraph(config=config)
    final_state, signal = graph.propagate(ticker, date)
    
    return {
        "ticker": ticker,
        "date": date,
        "state": final_state,
        "signal": signal,
        "reports": {
            "market": final_state.get("market_report"),
            "sentiment": final_state.get("sentiment_report"),
            "news": final_state.get("news_report"),
            "fundamentals": final_state.get("fundamentals_report"),
            "decision": final_state.get("final_trade_decision"),
        }
    }
```

---

## 6. Quick Start Comparison

| Option | Setup Command | Launch Command |
|--------|--------------|----------------|
| **FastAPI** | `pip install fastapi uvicorn sse-starlette` | `uvicorn web.app:app --reload` |
| **Streamlit** | `pip install streamlit` | `streamlit run web/streamlit_app.py` |
| **Gradio** | `pip install gradio` | `python web/gradio_app.py` |
| **Full-Stack** | `npm create vite@latest` + `pip install fastapi` | `npm run dev` + `uvicorn web.app:app` |

---

## 7. Recommendation

| Use Case | Recommended Option |
|----------|-------------------|
| **Quick prototype / internal use** | Option D (Gradio) |
| **Single-developer project** | Option B (Streamlit) |
| **Production deployment** | Option A (FastAPI) |
| **Team collaboration / public SaaS** | Option C (Full-Stack) |

**For most TradingAgents users, I recommend Option A (FastAPI + simple HTML/JS frontend)** because:
1. The core logic is already well-structured and async-ready
2. SSE provides real-time updates without WebSocket complexity
3. The frontend can start simple (vanilla JS) and evolve to React later
4. Docker deployment is straightforward
5. API-first design enables future mobile app development
