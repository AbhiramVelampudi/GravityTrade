"""
Agent 1: Orchestrator
Master supervisor coordinating all 14 agents in dependency order.
Broadcasts real-time status after EVERY agent so the dashboard never shows stale IDLE.
"""
import asyncio
import json
import logging
from datetime import datetime

from core.state import PortfolioState
from agents.portfolio_ingestor     import PortfolioIngestorAgent
from agents.market_data_agent      import MarketDataAgent
from agents.technical_analysis     import TechnicalAnalysisAgent
from agents.fundamental_analysis   import FundamentalAnalysisAgent
from agents.sentiment_analysis     import SentimentAnalysisAgent
from agents.macro_intelligence     import MacroIntelligenceAgent
from agents.bull_agent             import BullAgent
from agents.bear_agent             import BearAgent
from agents.pattern_recognition    import PatternRecognitionAgent
from agents.risk_manager           import RiskManagerAgent
from agents.time_precision_advisor import TimePrecisionAdvisorAgent
from agents.portfolio_strategist   import PortfolioStrategistAgent
from agents.stock_scanner          import StockScannerAgent
from agents.preference_scanner     import PreferenceScannerAgent
from agents.smart_money_agent      import SmartMoneyAgent

logger = logging.getLogger("Orchestrator")


class OrchestratorAgent:
    """Master coordinator for all 14 GravityTrade portfolio agents."""

    name = "Orchestrator"

    def __init__(self, verbose: bool = True, api_key: str = ""):
        self.verbose  = verbose
        self.state    = PortfolioState()
        self.state.settings["gemini_api_key"] = api_key
        self.state.agent_statuses["Orchestrator"] = "IDLE"
        self.state.agent_logs["Orchestrator"]     = []
        self.ws_broadcaster = None   # Set by server for live WebSocket streaming

    def log(self, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] [Orchestrator] {msg}"
        self.state.agent_logs["Orchestrator"].append(entry)
        if self.verbose:
            logger.info(msg)

    def _set_status(self, status: str):
        self.state.agent_statuses["Orchestrator"] = status

    # ── WebSocket helpers ─────────────────────────────────────────────
    async def _broadcast(self, event: str, data: dict = None):
        """Push a named event to all WebSocket clients. Never raises."""
        if self.ws_broadcaster:
            try:
                msg = json.dumps({"event": event, "data": data or {}},
                                 default=str, allow_nan=False)
            except (ValueError, TypeError):
                # inf/nan in data → strip them and retry
                import math
                def _sanitize(o):
                    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
                        return None
                    if isinstance(o, dict):
                        return {k: _sanitize(v) for k, v in o.items()}
                    if isinstance(o, (list, tuple)):
                        return [_sanitize(i) for i in o]
                    return o
                try:
                    msg = json.dumps({"event": event, "data": _sanitize(data or {})},
                                     default=str)
                except Exception:
                    return
            try:
                await self.ws_broadcaster(msg)
            except Exception:
                pass

    async def _push_statuses(self):
        """Immediately push all current agent statuses — called after every phase/agent."""
        try:
            payload = {
                "agent_statuses": self.state.agent_statuses,
                "agent_logs": {k: v[-3:] for k, v in self.state.agent_logs.items()},
            }
            await self._broadcast("status_update", payload)
        except Exception:
            pass   # never crash the pipeline for a status push

    async def _run_agent(self, agent) -> None:
        """Run one agent and immediately push status before AND after."""
        await self._push_statuses()                        # push RUNNING
        await agent.safe_run()
        await self._push_statuses()                        # push DONE / ERROR
        await self._broadcast("agent_done", {"agent": agent.name, "status": self.state.agent_statuses.get(agent.name)})

    async def _run_parallel(self, *agents) -> None:
        """Run agents in parallel; push statuses before and after the whole group."""
        await self._push_statuses()
        await asyncio.gather(*[a.safe_run() for a in agents])
        await self._push_statuses()

    # ── Main Pipeline ─────────────────────────────────────────────────
    async def run(self) -> PortfolioState:
        """
        14-agent execution pipeline:

        PHASE 1 (Sequential): PortfolioIngestor → MarketData
        PHASE 2 (Parallel):   TA + Fundamentals + Sentiment + Macro
        PHASE 3 (Parallel):   Bull + Bear + Pattern + StockScanner
        PHASE 4 (Sequential): RiskManager → TimePrecision → Strategist
        """
        self._set_status("RUNNING")
        self.log("🚀 GRAVITYTRADE STOCK INTELLIGENCE SYSTEM — INITIATING")
        self.log("=" * 60)
        start = datetime.now()

        # ── PHASE 1 ────────────────────────────────────────────────────
        self.log("📦 PHASE 1: Data Ingestion")
        await self._broadcast("phase_start", {"phase": 1, "name": "Data Ingestion"})

        ingestor = PortfolioIngestorAgent(self.state, self.verbose)
        await self._run_agent(ingestor)

        if not self.state.holdings:
            self.log("❌ No holdings found — aborting pipeline.")
            self._set_status("ERROR")
            await self._push_statuses()
            return self.state

        market = MarketDataAgent(self.state, self.verbose)
        await self._run_agent(market)

        # ── PHASE 2 ────────────────────────────────────────────────────
        self.log("🔬 PHASE 2: Parallel Analysis (TA + Fundamentals + Sentiment + Macro)")
        await self._broadcast("phase_start", {"phase": 2, "name": "Parallel Analysis"})

        ta      = TechnicalAnalysisAgent(self.state, self.verbose)
        fund    = FundamentalAnalysisAgent(self.state, self.verbose)
        sent    = SentimentAnalysisAgent(self.state, self.verbose)
        macro   = MacroIntelligenceAgent(self.state, self.verbose)
        smart   = SmartMoneyAgent(self.state, self.verbose)

        await self._run_parallel(ta, fund, sent, macro, smart)
        await self._broadcast("phase_done", {"phase": 2})

        # ── PHASE 3 ────────────────────────────────────────────────────
        self.log("⚔️  PHASE 3: Bull/Bear Debate + Pattern + Stock Scanner")
        await self._broadcast("phase_start", {"phase": 3, "name": "Bull/Bear Debate + Scanner"})

        bull    = BullAgent(self.state, self.verbose)
        bear    = BearAgent(self.state, self.verbose)
        pattern = PatternRecognitionAgent(self.state, self.verbose)
        scanner = StockScannerAgent(self.state, self.verbose)
        pref    = PreferenceScannerAgent(self.state, self.verbose)

        await self._run_parallel(bull, bear, pattern, scanner, pref)
        await self._broadcast("phase_done", {"phase": 3})

        # ── PHASE 4 ────────────────────────────────────────────────────
        self.log("🏆 PHASE 4: Risk Management → Time Precision → Final Strategy")
        await self._broadcast("phase_start", {"phase": 4, "name": "Risk & Strategy"})

        risk = RiskManagerAgent(self.state, self.verbose)
        await self._run_agent(risk)

        timing = TimePrecisionAdvisorAgent(self.state, self.verbose)
        await self._run_agent(timing)

        strategy = PortfolioStrategistAgent(self.state, self.verbose)
        await self._run_agent(strategy)

        # ── DONE ───────────────────────────────────────────────────────
        elapsed = (datetime.now() - start).total_seconds()
        self._set_status("DONE")
        self.log(f"✅ Analysis complete in {elapsed:.1f}s | {len(self.state.holdings)} portfolio + {len(self.state.scan_recommendations)} new picks")
        await self._push_statuses()

        return self.state
