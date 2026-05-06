"""SSE (Server-Sent Events) emitter for real-time analysis updates."""

import asyncio
import json
import uuid
import logging
from typing import Dict, Any, AsyncGenerator, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class AnalysisEvent:
    """Represents a single event in the analysis pipeline."""
    
    def __init__(self, event_type: str, data: Dict[str, Any], task_id: str):
        self.event_type = event_type
        self.data = data
        self.task_id = task_id
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.event_id = str(uuid.uuid4())[:8]
    
    def to_sse_format(self) -> str:
        """Format as SSE string."""
        payload = {
            "id": self.event_id,
            "type": self.event_type,
            "task_id": self.task_id,
            "timestamp": self.timestamp,
            "data": self.data
        }
        return f"id: {self.event_id}\nevent: {self.event_type}\ndata: {json.dumps(payload)}\n\n"


class EventEmitter:
    """Manages event emission for a single analysis task."""
    
    def __init__(self, task_id: str):
        self.task_id = task_id
        self._queue: asyncio.Queue = asyncio.Queue()
        self._subscribers: list[asyncio.Queue] = []
        self._completed = False
    
    async def emit(self, event_type: str, data: Dict[str, Any]):
        """Emit an event to all subscribers."""
        event = AnalysisEvent(event_type, data, self.task_id)
        sse_string = event.to_sse_format()
        
        # Put in queue for streaming
        await self._queue.put(sse_string)
        
        logger.debug(f"Emitted event {event_type} for task {self.task_id}")
    
    async def emit_progress(self, step: str, progress: float, message: str = ""):
        """Emit a progress update event."""
        await self.emit("progress", {
            "step": step,
            "progress": progress,
            "message": message
        })
    
    async def emit_report(self, report_type: str, content: str):
        """Emit an analyst report event."""
        await self.emit("report", {
            "type": report_type,
            "content": content
        })
    
    async def emit_decision(self, decision: str):
        """Emit the final trading decision."""
        await self.emit("decision", {"content": decision})
    
    async def emit_signal(self, signal: Dict[str, Any]):
        """Emit the processed signal."""
        await self.emit("signal", signal)
    
    async def emit_error(self, error: str):
        """Emit an error event."""
        await self.emit("error", {"message": error})
        self._completed = True
    
    async def emit_complete(self, result: Dict[str, Any]):
        """Emit completion event with final result."""
        await self.emit("complete", result)
        self._completed = True
    
    async def emit_agent_status(self, agent_name: str, status: str, message: str = ""):
        """Emit an agent status update event.
        
        Args:
            agent_name: Name of the agent (e.g., "Market Analyst", "Trader")
            status: Status string - "pending", "in_progress", "completed", "error"
            message: Optional status message
        """
        await self.emit("agent_status", {
            "agent": agent_name,
            "status": status,
            "message": message
        })
    
    async def event_generator(self) -> AsyncGenerator[str, None]:
        """Generate SSE events for streaming to client."""
        # Send initial connection event
        initial = AnalysisEvent("connected", {
            "task_id": self.task_id,
            "message": "Connected to analysis stream"
        }, self.task_id)
        yield initial.to_sse_format()
        
        try:
            while not self._completed:
                try:
                    # Wait for event with timeout
                    sse_string = await asyncio.wait_for(
                        self._queue.get(), timeout=30.0
                    )
                    yield sse_string
                except asyncio.TimeoutError:
                    # Send keepalive to prevent connection timeout
                    yield ": keepalive\n\n"
        except GeneratorExit:
            logger.info(f"SSE connection closed for task {self.task_id}")


class TaskManager:
    """Manages all active analysis tasks."""
    
    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}
        self._emitters: Dict[str, EventEmitter] = {}
        self._results: Dict[str, Dict[str, Any]] = {}
    
    def create_task(self, task_id: str) -> EventEmitter:
        """Create a new task emitter."""
        emitter = EventEmitter(task_id)
        self._emitters[task_id] = emitter
        return emitter
    
    def get_emitter(self, task_id: str) -> Optional[EventEmitter]:
        """Get emitter for a task."""
        return self._emitters.get(task_id)
    
    def set_result(self, task_id: str, result: Dict[str, Any]):
        """Store task result."""
        self._results[task_id] = result
        self._tasks.pop(task_id, None)
    
    def get_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get stored result for a task."""
        return self._results.get(task_id)
    
    def list_tasks(self) -> Dict[str, str]:
        """List all active task IDs and their status."""
        return {
            tid: "running" if tid in self._tasks else "completed"
            for tid in self._emitters
        }


# Global task manager instance
task_manager = TaskManager()
