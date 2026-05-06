"""Background task runner for TradingAgents analysis execution."""

import asyncio
import logging
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from web.config import apply_web_config, ANALYST_OPTIONS
from web.events import task_manager, EventEmitter

logger = logging.getLogger(__name__)

# Ordered list of analysts for status transitions (matches CLI)
ANALYST_ORDER = ["market", "social", "news", "fundamentals"]
ANALYST_AGENT_NAMES = {
    "market": "Market Analyst",
    "social": "Social Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}
ANALYST_REPORT_MAP = {
    "market": "market_report",
    "social": "sentiment_report",
    "news": "news_report",
    "fundamentals": "fundamentals_report",
}

# Agent status constants
STATUS_PENDING = "pending"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_ERROR = "error"

# Agent teams for display
AGENT_TEAMS = {
    "Analyst Team": [
        "Market Analyst", "Social Analyst", "News Analyst", "Fundamentals Analyst"
    ],
    "Research Team": ["Bull Researcher", "Bear Researcher", "Research Manager"],
    "Trading Team": ["Trader"],
    "Risk Management": ["Aggressive Analyst", "Neutral Analyst", "Conservative Analyst"],
    "Portfolio Management": ["Portfolio Manager"],
}


def _extract_error_details(exception: Exception) -> Optional[str]:
    """Extract connection-related details from an exception.
    
    Attempts to extract target URL, host, port, and other connection details
    from common HTTP client exceptions (httpx, OpenAI, requests).
    
    Args:
        exception: The exception to extract details from
        
    Returns:
        Formatted string with connection details, or None if no details found
    """
    details = []
    
    # Try httpx exceptions (used by OpenAI client internally)
    request = getattr(exception, "request", None)
    if request is None:
        # Some exceptions wrap the request in a response object
        response = getattr(exception, "response", None)
        if response is not None:
            request = getattr(response, "request", None)
    
    if request is not None:
        # Get URL details
        url = getattr(request, "url", None)
        if url is not None:
            # httpx.URL objects have host, port, scheme attributes
            host = getattr(url, "host", None) or getattr(url, "hostname", None)
            port = getattr(url, "port", None)
            scheme = getattr(url, "scheme", None)
            path = getattr(request, "path", None) or (str(url) if url else None)
            
            if host:
                details.append(f"host={host}")
            if port:
                details.append(f"port={port}")
            if scheme:
                details.append(f"scheme={scheme}")
            
            # Try to get full URL string
            try:
                full_url = str(url)
                if full_url:
                    details.append(f"url={full_url}")
            except (AttributeError, TypeError):
                pass
        
        # Get method and path from request
        method = getattr(request, "method", None)
        if method:
            details.append(f"method={method}")
    
    # Try to get status code from response
    response = getattr(exception, "response", None)
    if response is not None:
        status = getattr(response, "status_code", None)
        if status:
            details.append(f"status={status}")
        # Get response headers/body if available
        headers = getattr(response, "headers", None)
        if headers:
            try:
                retry_after = headers.get("retry-after") or headers.get(b"retry-after")
                if retry_after:
                    details.append(f"retry-after={retry_after}")
            except (AttributeError, TypeError):
                pass
    
    # Check for nested exceptions
    cause = getattr(exception, "__cause__", None)
    if cause is not None and cause is not exception:
        nested = _extract_error_details(cause)
        if nested:
            details.append(f"nested: {nested}")
    
    # Check for inner exception (common in .NET interop or wrapped exceptions)
    inner = getattr(exception, "inner_exception", None)
    if inner is not None:
        inner_details = _extract_error_details(inner)
        if inner_details:
            details.append(f"inner: {inner_details}")
    
    return ", ".join(details) if details else None


# ============================================================================
# Agent Status Tracking Helpers (mirrors CLI main.py logic)
# ============================================================================

def _init_agent_status(selected_analysts: List[str]) -> Dict[str, str]:
    """Initialize agent status dict based on selected analysts."""
    status = {}
    # Add selected analysts
    for key in selected_analysts:
        if key in ANALYST_AGENT_NAMES:
            status[ANALYST_AGENT_NAMES[key]] = STATUS_PENDING
    # Add fixed teams
    for team_agents in AGENT_TEAMS.values():
        for agent in team_agents:
            status[agent] = STATUS_PENDING
    return status


def _update_analyst_statuses(
    agent_status: Dict[str, str],
    report_sections: Dict[str, Optional[str]],
    chunk: Dict[str, Any],
    selected_analysts: List[str],
    emitter: EventEmitter,
) -> None:
    """Update analyst statuses based on accumulated report state.
    
    Logic:
    - Store new report content from current chunk if present
    - Analysts with reports = completed
    - First analyst without report = in_progress
    - Remaining analysts without reports = pending
    - When all analysts done, transition Bull Researcher to in_progress
    """
    found_active = False
    
    for analyst_key in ANALYST_ORDER:
        if analyst_key not in selected_analysts:
            continue
        
        agent_name = ANALYST_AGENT_NAMES[analyst_key]
        report_key = ANALYST_REPORT_MAP[analyst_key]
        
        # Capture new report content from current chunk
        if chunk.get(report_key):
            report_sections[report_key] = chunk[report_key]
        
        # Determine status from accumulated sections
        has_report = bool(report_sections.get(report_key))
        
        if has_report:
            agent_status[agent_name] = STATUS_COMPLETED
            found_active = True  # This analyst was already in_progress, now done
            # Emit completion event
            asyncio.create_task(emitter.emit_agent_status(agent_name, STATUS_COMPLETED))
        elif not found_active:
            agent_status[agent_name] = STATUS_IN_PROGRESS
            # Emit in_progress event (only if changed from pending)
            if agent_status.get(agent_name) == STATUS_PENDING:
                asyncio.create_task(emitter.emit_agent_status(agent_name, STATUS_IN_PROGRESS))
        else:
            agent_status[agent_name] = STATUS_PENDING
    
    # When all analysts complete, transition Bull Researcher to in_progress
    all_analysts_done = True
    for analyst_key in selected_analysts:
        if analyst_key in ANALYST_REPORT_MAP:
            report_key = ANALYST_REPORT_MAP[analyst_key]
            if not report_sections.get(report_key):
                all_analysts_done = False
                break
    
    if all_analysts_done and selected_analysts:
        if agent_status.get("Bull Researcher") == STATUS_PENDING:
            agent_status["Bull Researcher"] = STATUS_IN_PROGRESS
            asyncio.create_task(emitter.emit_agent_status("Bull Researcher", STATUS_IN_PROGRESS))


def _update_research_team_status(
    agent_status: Dict[str, str],
    status: str,
    emitter: EventEmitter,
) -> None:
    """Update status for research team members."""
    for agent in ["Bull Researcher", "Bear Researcher", "Research Manager"]:
        if agent_status.get(agent) != status:
            agent_status[agent] = status
            asyncio.create_task(emitter.emit_agent_status(agent, status))


def _process_chunk(
    chunk: Dict[str, Any],
    agent_status: Dict[str, str],
    report_sections: Dict[str, Optional[str]],
    selected_analysts: List[str],
    emitter: EventEmitter,
) -> None:
    """Process a single graph chunk and update agent statuses.
    
    This mirrors the CLI's chunk processing logic in main.py lines 1056-1153.
    """
    # Update analyst statuses based on report state
    _update_analyst_statuses(agent_status, report_sections, chunk, selected_analysts, emitter)
    
    # Research Team - Handle Investment Debate State
    if chunk.get("investment_debate_state"):
        debate_state = chunk["investment_debate_state"]
        bull_hist = debate_state.get("bull_history", "").strip()
        bear_hist = debate_state.get("bear_history", "").strip()
        judge = debate_state.get("judge_decision", "").strip()
        
        # Only update status when there's actual content
        if bull_hist or bear_hist:
            _update_research_team_status(agent_status, STATUS_IN_PROGRESS, emitter)
        
        if bull_hist:
            report_sections["investment_plan"] = f"### Bull Researcher Analysis\n{bull_hist}"
        
        if bear_hist:
            report_sections["investment_plan"] = f"### Bear Researcher Analysis\n{bear_hist}"
        
        if judge:
            report_sections["investment_plan"] = f"### Research Manager Decision\n{judge}"
            _update_research_team_status(agent_status, STATUS_COMPLETED, emitter)
            # Transition Trader to in_progress
            if agent_status.get("Trader") != STATUS_COMPLETED:
                agent_status["Trader"] = STATUS_IN_PROGRESS
                asyncio.create_task(emitter.emit_agent_status("Trader", STATUS_IN_PROGRESS))
    
    # Trading Team
    if chunk.get("trader_investment_plan"):
        report_sections["trader_investment_plan"] = chunk["trader_investment_plan"]
        if agent_status.get("Trader") != STATUS_COMPLETED:
            agent_status["Trader"] = STATUS_COMPLETED
            asyncio.create_task(emitter.emit_agent_status("Trader", STATUS_COMPLETED))
            # Transition Aggressive Analyst to in_progress
            agent_status["Aggressive Analyst"] = STATUS_IN_PROGRESS
            asyncio.create_task(emitter.emit_agent_status("Aggressive Analyst", STATUS_IN_PROGRESS))
    
    # Risk Management Team - Handle Risk Debate State
    if chunk.get("risk_debate_state"):
        risk_state = chunk["risk_debate_state"]
        agg_hist = risk_state.get("aggressive_history", "").strip()
        con_hist = risk_state.get("conservative_history", "").strip()
        neu_hist = risk_state.get("neutral_history", "").strip()
        judge = risk_state.get("judge_decision", "").strip()
        
        if agg_hist:
            if agent_status.get("Aggressive Analyst") != STATUS_COMPLETED:
                agent_status["Aggressive Analyst"] = STATUS_IN_PROGRESS
                asyncio.create_task(emitter.emit_agent_status("Aggressive Analyst", STATUS_IN_PROGRESS))
            report_sections["final_trade_decision"] = f"### Aggressive Analyst Analysis\n{agg_hist}"
        
        if con_hist:
            if agent_status.get("Conservative Analyst") != STATUS_COMPLETED:
                agent_status["Conservative Analyst"] = STATUS_IN_PROGRESS
                asyncio.create_task(emitter.emit_agent_status("Conservative Analyst", STATUS_IN_PROGRESS))
            report_sections["final_trade_decision"] = f"### Conservative Analyst Analysis\n{con_hist}"
        
        if neu_hist:
            if agent_status.get("Neutral Analyst") != STATUS_COMPLETED:
                agent_status["Neutral Analyst"] = STATUS_IN_PROGRESS
                asyncio.create_task(emitter.emit_agent_status("Neutral Analyst", STATUS_IN_PROGRESS))
            report_sections["final_trade_decision"] = f"### Neutral Analyst Analysis\n{neu_hist}"
        
        if judge:
            if agent_status.get("Portfolio Manager") != STATUS_COMPLETED:
                agent_status["Portfolio Manager"] = STATUS_IN_PROGRESS
                report_sections["final_trade_decision"] = f"### Portfolio Manager Decision\n{judge}"
                # Complete all risk team members and portfolio manager
                agent_status["Aggressive Analyst"] = STATUS_COMPLETED
                agent_status["Conservative Analyst"] = STATUS_COMPLETED
                agent_status["Neutral Analyst"] = STATUS_COMPLETED
                agent_status["Portfolio Manager"] = STATUS_COMPLETED
                
                # Emit completion events for all
                for agent in ["Aggressive Analyst", "Conservative Analyst", "Neutral Analyst", "Portfolio Manager"]:
                    asyncio.create_task(emitter.emit_agent_status(agent, STATUS_COMPLETED))


async def run_analysis(
    ticker: str,
    date: str,
    analysts: List[str],
    config_overrides: Optional[Dict[str, Any]] = None
):
    """Run the full TradingAgents analysis pipeline.
    
    This function executes the trading agents graph and emits SSE events
    for each major step in the pipeline.
    
    Args:
        ticker: Stock ticker symbol
        date: Analysis date (YYYY-MM-DD)
        analysts: List of analyst types to include
        config_overrides: Optional configuration overrides
        
    Returns:
        Dict containing the final result
    """
    task_id = str(uuid.uuid4())[:8]
    logger.info(f"Starting analysis task {task_id} for {ticker} on {date}")
    
    # Create event emitter for this task
    emitter = task_manager.create_task(task_id)
    
    # Track progress percentage
    progress = {"value": 5}
    
    async def update_progress(step: str, increment: int, message: str):
        """Helper to update progress and emit event."""
        progress["value"] = min(100, progress["value"] + increment)
        await emitter.emit_progress(step, progress["value"], message)
    
    try:
        # Step 1: Setup
        await update_progress("initializing", 5, "Setting up analysis...")
        
        # Build configuration
        base_config = apply_web_config(config_overrides or {})
        
        # Update analysts in config
        if analysts:
            base_config["selected_analysts"] = analysts
        
        await update_progress("configuring", 5, "Configuring agents...")
        
        # Initialize TradingAgentsGraph
        graph = TradingAgentsGraph(
            selected_analysts=analysts or ["market", "social", "news", "fundamentals"],
            debug=False,
            config=base_config
        )
        
        await update_progress("loading", 10, "Loading market data...")
        
        # Initialize agent status tracking
        selected_analysts = analysts or ["market", "social", "news", "fundamentals"]
        agent_status = _init_agent_status(selected_analysts)
        report_sections: Dict[str, Optional[str]] = {}
        
        # Initialize state and get graph args
        init_agent_state = graph.propagator.create_initial_state(
            ticker, date
        )
        args = graph.propagator.get_graph_args()
        
        # Emit initial agent statuses
        for agent, status in agent_status.items():
            await emitter.emit_agent_status(agent, status)
        
        # Step 2: Stream graph chunks in real-time
        # Run the graph execution in a thread pool, but process chunks synchronously
        trace = []
        chunk_queue: asyncio.Queue = asyncio.Queue()
        total_chunks = 0
        processed_chunks = 0
        
        def run_graph_and_queue_chunks():
            """Run graph.stream() and put chunks into queue."""
            nonlocal total_chunks
            try:
                for chunk in graph.graph.stream(init_agent_state, **args):
                    total_chunks += 1
                    chunk_queue.put_nowait(chunk)
            except Exception as e:
                logger.error(f"Graph execution error in thread: {e}")
            finally:
                chunk_queue.put_nowait(None)  # Sentinel to signal completion
        
        # Start graph execution in background thread
        graph_task = asyncio.create_task(asyncio.to_thread(run_graph_and_queue_chunks))
        
        # Process chunks as they arrive
        while True:
            chunk = await chunk_queue.get()
            if chunk is None:  # Sentinel received
                break
            
            processed_chunks += 1
            trace.append(chunk)
            
            # Process chunk and update agent statuses (synchronous)
            _process_chunk(chunk, agent_status, report_sections, selected_analysts, emitter)
            
            # Update progress based on chunks processed (20% -> 85% range)
            if total_chunks > 0:
                chunk_progress = int((processed_chunks / total_chunks) * 65)  # 65% for chunk processing
                await update_progress("analyzing", 20 + chunk_progress, 
                                    f"Processing {processed_chunks}/{total_chunks} chunks...")
            
            # Yield control to allow event emission
            await asyncio.sleep(0)
        
        # Wait for graph thread to complete
        await graph_task
        
        await update_progress("processing", 30, "Processing results...")
        
        # Emit individual reports (from final state)
        final_state = trace[-1] if trace else {}
        
        for report_type in ["market_report", "sentiment_report", "news_report", "fundamentals_report"]:
            content = final_state.get(report_type, "")
            if content:
                await emitter.emit_report(report_type, content)
        
        # Emit investment plan
        investment_plan = final_state.get("investment_plan", "")
        if investment_plan:
            await emitter.emit_report("investment_plan", investment_plan)
        
        # Emit final decision
        decision = final_state.get("final_trade_decision", "")
        if decision:
            await emitter.emit_decision(decision)
        
        await update_progress("finalizing", 5, "Finalizing results...")
        
        # Process signal
        signal = graph.process_signal(decision) if decision else ""
        
        # Build result
        result = {
            "ticker": ticker,
            "date": date,
            "signal": signal,
            "decision": decision,
            "timestamp": datetime.now().isoformat(),
            "analysts": analysts,
            "reports": {
                "market_report": final_state.get("market_report", ""),
                "sentiment_report": final_state.get("sentiment_report", ""),
                "news_report": final_state.get("news_report", ""),
                "fundamentals_report": final_state.get("fundamentals_report", ""),
                "investment_plan": final_state.get("investment_plan", ""),
            }
        }
        
        # Emit completion
        await emitter.emit_complete(result)
        
        # Store result in task manager
        task_manager.set_result(task_id, result)
        
        logger.info(f"Analysis task {task_id} completed successfully")
        
    except Exception as e:
        # Extract connection error details for enhanced logging
        error_details = _extract_error_details(e)
        if error_details:
            logger.error(f"Analysis task {task_id} failed: {e}\nConnection details: {error_details}", exc_info=True)
        else:
            logger.error(f"Analysis task {task_id} failed: {e}", exc_info=True)
        
        # Emit error event
        await emitter.emit_error(str(e))
        
        # Store error in task manager
        task_manager.set_result(task_id, {"error": str(e)})


def get_task_status(task_id: str) -> Dict[str, Any]:
    """Get the status of a task.
    
    Args:
        task_id: Task identifier
        
    Returns:
        Dict containing task status information
    """
    emitter = task_manager.get_emitter(task_id)
    result = task_manager.get_result(task_id)
    
    if emitter is None and result is None:
        return {"status": "not_found", "task_id": task_id}
    
    if result is not None:
        if "error" in result:
            return {
                "status": "error",
                "task_id": task_id,
                "error": result["error"]
            }
        return {
            "status": "completed",
            "task_id": task_id,
            "result": result
        }
    
    return {"status": "running", "task_id": task_id}
