"""FastAPI application for TradingAgents Web Interface."""

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.encoders import jsonable_encoder

from web.config import SERVER_HOST, SERVER_PORT, DEBUG, get_safe_config, ANALYST_OPTIONS, LLM_PROVIDER_OPTIONS
from web.models import AnalysisRequest, AnalysisResponse, TaskStatus, ConfigResponse
from web.events import task_manager
from web.runner import run_analysis, get_task_status

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    logger.info("TradingAgents Web Interface starting on %s:%s", SERVER_HOST, SERVER_PORT)
    yield
    logger.info("TradingAgents Web Interface shutting down")


app = FastAPI(
    title="TradingAgents Web Interface",
    description="Web-based interface for the TradingAgents multi-agent LLM trading framework",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# HTML Frontend
# =============================================================================

async def get_frontend_html() -> str:
    """Read the frontend HTML file."""
    try:
        with open("web/static/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>TradingAgents</title>
    <style>
        body { font-family: system-ui, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #1a1a2e; color: #eee; }
        h1 { color: #00d4ff; }
        .form-group { margin: 15px 0; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        input, select { padding: 8px; border: 1px solid #333; border-radius: 4px; background: #16213e; color: #eee; }
        button { padding: 10px 20px; background: #00d4ff; color: #1a1a2e; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; }
        button:hover { background: #00b8d4; }
        button:disabled { background: #555; cursor: not-allowed; }
        .analyst-check { display: inline-block; margin: 5px 15px; }
        #status { margin: 20px 0; padding: 15px; background: #16213e; border-radius: 8px; }
        .progress-bar { height: 8px; background: #333; border-radius: 4px; overflow: hidden; margin: 10px 0; }
        .progress-fill { height: 100%; background: linear-gradient(90deg, #00d4ff, #00ff88); transition: width 0.3s; }
        .report-section { margin: 15px 0; padding: 15px; background: #16213e; border-radius: 8px; border-left: 4px solid #00d4ff; }
        .report-section h3 { margin-top: 0; color: #00d4ff; }
        .decision { background: #0f3460; border-left-color: #00ff88; }
        .error { background: #3d0000; border-left-color: #ff4444; }
        pre { white-space: pre-wrap; word-wrap: break-word; font-family: inherit; }
    </style>
</head>
<body>
    <h1>TradingAgents</h1>
    <p>Multi-Agent LLM Trading Framework</p>
    
    <div class="form-group">
        <label for="ticker">Ticker Symbol</label>
        <input type="text" id="ticker" value="SPY" placeholder="e.g., SPY, AAPL, NVDA">
    </div>
    
    <div class="form-group">
        <label for="date">Analysis Date</label>
        <input type="date" id="date">
    </div>
    
    <div class="form-group">
        <label>Analysts</label>
        <span class="analyst-check"><input type="checkbox" id="a_market" checked> Market</span>
        <span class="analyst-check"><input type="checkbox" id="a_social" checked> Social</span>
        <span class="analyst-check"><input type="checkbox" id="a_news" checked> News</span>
        <span class="analyst-check"><input type="checkbox" id="a_fundamentals" checked> Fundamentals</span>
    </div>
    
    <div class="form-group">
        <button id="runBtn" onclick="startAnalysis()">Run Analysis</button>
    </div>
    
    <div id="status" style="display:none;">
        <h3 id="statusTitle">Analysis in Progress</h3>
        <div class="progress-bar"><div class="progress-fill" id="progressFill" style="width: 0%"></div></div>
        <p id="statusMessage">Initializing...</p>
    </div>
    
    <div id="results"></div>
    
    <script>
        // Set default date to today
        document.getElementById('date').valueAsDate = new Date();
        
        async function startAnalysis() {
            const ticker = document.getElementById('ticker').value.trim();
            const date = document.getElementById('date').value;
            const analysts = [];
            if (document.getElementById('a_market').checked) analysts.push('market');
            if (document.getElementById('a_social').checked) analysts.push('social');
            if (document.getElementById('a_news').checked) analysts.push('news');
            if (document.getElementById('a_fundamentals').checked) analysts.push('fundamentals');
            
            if (!ticker || !date) {
                alert('Please enter ticker and date');
                return;
            }
            
            const btn = document.getElementById('runBtn');
            btn.disabled = true;
            btn.textContent = 'Running...';
            
            const statusDiv = document.getElementById('status');
            statusDiv.style.display = 'block';
            document.getElementById('results').innerHTML = '';
            
            // Start SSE connection
            const task_id = await submitAnalysis(ticker, date, analysts);
            if (task_id) {
                connectToStream(task_id);
            }
            
            btn.disabled = false;
            btn.textContent = 'Run Analysis';
        }
        
        async function submitAnalysis(ticker, date, analysts) {
            try {
                const resp = await fetch('/api/analyze', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ticker, date, analysts})
                });
                const data = await resp.json();
                return data.task_id;
            } catch (err) {
                console.error('Failed to submit analysis:', err);
                return null;
            }
        }
        
        function connectToStream(task_id) {
            const eventSource = new EventSource(`/api/events/${task_id}`);
            
            eventSource.onmessage = function(event) {
                const data = JSON.parse(event.data);
                updateStatus(data);
            };
            
            eventSource.addEventListener('report', function(event) {
                const data = JSON.parse(event.data);
                addReportSection(data.type, data.content);
            });
            
            eventSource.addEventListener('decision', function(event) {
                const data = JSON.parse(event.data);
                addDecisionSection(data.content);
            });
            
            eventSource.addEventListener('complete', function(event) {
                const data = JSON.parse(event.data);
                document.getElementById('statusTitle').textContent = 'Analysis Complete';
                document.getElementById('statusMessage').textContent = 'Finished at ' + data.timestamp;
                eventSource.close();
            });
            
            eventSource.addEventListener('error', function(event) {
                const data = JSON.parse(event.data);
                document.getElementById('statusTitle').textContent = 'Analysis Failed';
                document.getElementById('statusMessage').textContent = data.message;
                addErrorSection(data.message);
                eventSource.close();
            });
        }
        
        function updateStatus(data) {
            const fill = document.getElementById('progressFill');
            const msg = document.getElementById('statusMessage');
            if (data.data && data.data.progress !== undefined) {
                fill.style.width = data.data.progress + '%';
                msg.textContent = data.data.step + ': ' + (data.data.message || '');
            }
        }
        
        function addReportSection(type, content) {
            const results = document.getElementById('results');
            const labels = {
                market_report: 'Market Analysis',
                sentiment_report: 'Social Media Sentiment',
                news_report: 'News Analysis',
                fundamentals_report: 'Fundamentals Analysis',
                investment_plan: 'Investment Plan'
            };
            const div = document.createElement('div');
            div.className = 'report-section';
            div.innerHTML = '<h3>' + (labels[type] || type) + '</h3><pre>' + escapeHtml(content || '') + '</pre>';
            results.appendChild(div);
        }
        
        function addDecisionSection(content) {
            const results = document.getElementById('results');
            const div = document.createElement('div');
            div.className = 'report-section decision';
            div.innerHTML = '<h3>Final Trade Decision</h3><pre>' + escapeHtml(content || '') + '</pre>';
            results.appendChild(div);
        }
        
        function addErrorSection(message) {
            const results = document.getElementById('results');
            const div = document.createElement('div');
            div.className = 'report-section error';
            div.innerHTML = '<h3>Error</h3><pre>' + escapeHtml(message) + '</pre>';
            results.appendChild(div);
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    </script>
</body>
</html>"""


# =============================================================================
# API Endpoints
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the frontend HTML."""
    return await get_frontend_html()


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "active_tasks": len(task_manager.list_tasks()),
        "timestamp": asyncio.get_event_loop().time()
    }


@app.post("/api/analyze", response_model=AnalysisResponse)
async def start_analysis(request: AnalysisRequest, background_tasks: BackgroundTasks):
    """Start a new analysis task."""
    logger.info(f"Starting analysis for {request.ticker} on {request.date}")
    
    # Generate task ID
    task_id = str(uuid.uuid4())[:8]
    
    # Create event emitter
    task_manager.create_task(task_id)
    
    # Start analysis in background
    background_tasks.add_task(
        run_analysis,
        ticker=request.ticker,
        date=request.date,
        analysts=request.analysts,
        config_overrides=request.config
    )
    
    return AnalysisResponse(
        task_id=task_id,
        status="started",
        message=f"Analysis for {request.ticker} started"
    )


@app.get("/api/events/{task_id}")
async def event_stream(task_id: str):
    """SSE event stream for real-time updates."""
    emitter = task_manager.get_emitter(task_id)
    
    if emitter is None:
        # Check if result exists
        result = task_manager.get_result(task_id)
        if result:
            raise HTTPException(status_code=404, detail="Task not found or already expired")
        raise HTTPException(status_code=404, detail="Task not found")
    
    return StreamingResponse(
        emitter.event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/status/{task_id}", response_model=TaskStatus)
async def get_status(task_id: str):
    """Get the status of a task."""
    status = await get_task_status(task_id)
    
    if status["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Task not found")
    
    return TaskStatus(**status)


@app.get("/api/config", response_model=ConfigResponse)
async def get_config():
    """Get the current configuration (sanitized)."""
    return ConfigResponse(
        config=get_safe_config(),
        analysts=ANALYST_OPTIONS,
        llm_providers=LLM_PROVIDER_OPTIONS
    )


@app.get("/api/history")
async def get_history():
    """Get list of completed tasks."""
    tasks = task_manager.list_tasks()
    return {
        "tasks": [
            {"task_id": tid, "status": status}
            for tid, status in tasks.items()
        ]
    }


@app.get("/api/result/{task_id}")
async def get_result(task_id: str):
    """Get the final result of a completed task."""
    result = task_manager.get_result(task_id)
    
    if result is None:
        raise HTTPException(status_code=404, detail="Result not found or task still running")
    
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    
    return result


# =============================================================================
# Static Files
# =============================================================================

# Mount static files directory if it exists
import os
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "web.app:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=DEBUG
    )
