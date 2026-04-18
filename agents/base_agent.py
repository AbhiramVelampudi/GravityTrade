"""
Base Agent class — all 13 agents extend this.
Provides logging, state access, tool calling, and MCP protocol.
"""
import logging
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Optional
from datetime import datetime

from core.state import PortfolioState
from core.mcp_tools import get_registry


class BaseAgent(ABC):
    """Base class for all Antigravity portfolio agents."""

    name: str = "BaseAgent"
    description: str = ""
    version: str = "1.0.0"

    def __init__(self, state: PortfolioState, verbose: bool = True):
        self.state = state
        self.verbose = verbose
        self.logger = logging.getLogger(self.name)
        self._init_status()

    def _init_status(self):
        self.state.agent_statuses[self.name] = "IDLE"
        self.state.agent_logs[self.name] = []

    def log(self, msg: str, level: str = "info"):
        """Log a message and push to shared state."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] [{self.name}] {msg}"
        self.state.agent_logs[self.name].append(entry)
        if self.verbose:
            getattr(self.logger, level)(msg)

    def set_status(self, status: str):
        """Update this agent's status in shared state."""
        self.state.agent_statuses[self.name] = status
        self.log(f"Status → {status}")

    def use_tool(self, tool_name: str, **kwargs) -> Any:
        """MCP-style tool call with logging."""
        self.log(f"🔧 Calling tool: {tool_name}({', '.join(f'{k}={v}' for k,v in kwargs.items())})")
        try:
            return get_registry().call(tool_name, **kwargs)
        except Exception as e:
            self.log(f"❌ Tool error: {e}", level="error")
            raise

    @abstractmethod
    async def run(self) -> None:
        """Execute this agent's analysis. Must update self.state."""
        pass

    async def safe_run(self) -> None:
        """Run with error handling."""
        try:
            self.set_status("RUNNING")
            await self.run()
            self.set_status("DONE")
        except Exception as e:
            self.log(f"❌ Error: {e}", level="error")
            self.set_status("ERROR")
