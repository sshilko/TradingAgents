"""Pydantic models for API request/response validation."""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    """Request model for starting a new analysis."""
    ticker: str = Field(..., min_length=1, max_length=20, description="Ticker symbol (e.g., SPY, AAPL)")
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Analysis date (YYYY-MM-DD)")
    analysts: List[str] = Field(
        default=["market", "social", "news", "fundamentals"],
        description="List of analyst types to include"
    )
    config: Optional[Dict[str, Any]] = Field(default=None, description="Optional config overrides")


class AnalysisResponse(BaseModel):
    """Response model for analysis submission."""
    task_id: str
    status: str
    message: str


class TaskStatus(BaseModel):
    """Current status of a task."""
    task_id: str
    status: str  # pending, running, completed, failed
    progress: float = 0.0
    current_step: str = ""
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ConfigResponse(BaseModel):
    """Safe configuration response."""
    config: Dict[str, Any]
    analysts: List[Dict[str, str]]
    llm_providers: List[Dict[str, str]]


class HistoryEntry(BaseModel):
    """Entry in the analysis history."""
    task_id: str
    ticker: str
    date: str
    timestamp: str
    status: str
    decision_summary: Optional[str] = None
