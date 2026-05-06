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
    
    try:
        # Emit running status
        await emitter.emit_progress("initializing", 5, "Setting up analysis...")
        
        # Build configuration
        base_config = apply_web_config(config_overrides or {})
        
        # Update analysts in config
        if analysts:
            base_config["selected_analysts"] = analysts
        
        await emitter.emit_progress("configuring", 10, "Configuring agents...")
        
        # Initialize TradingAgentsGraph (no callbacks - we emit events manually)
        graph = TradingAgentsGraph(
            selected_analysts=analysts or ["market", "social", "news", "fundamentals"],
            debug=False,
            config=base_config
        )
        
        await emitter.emit_progress("loading", 20, "Loading market data...")
        
        # Run the analysis pipeline (blocking call in thread pool)
        final_state, signal = await asyncio.to_thread(
            graph.propagate, ticker, date
        )
        
        await emitter.emit_progress("processing", 85, "Processing results...")
        
        # Emit individual reports
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
        
        await emitter.emit_progress("finalizing", 95, "Finalizing results...")
        
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
