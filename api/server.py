"""
FastAPI server with WebSocket support for live agent status updates.
Serves the dashboard and provides REST API for analysis runs.
"""
import asyncio
import json
import logging
import os
import sys
import dataclasses
from datetime import datetime
from pathlib import Path
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
import uvicorn

# Make sure root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.orchestrator import OrchestratorAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S"
)

app = FastAPI(title="Antigravity Stock Intelligence", version="1.0.0")

# Mount dashboard static files
dashboard_path = Path(__file__).parent.parent / "dashboard"
app.mount("/static", StaticFiles(directory=str(dashboard_path)), name="static")

# WebSocket connection manager — bulletproof edition
class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self.active.add(ws)
        logging.info(f"WS connected. Total: {len(self.active)}")

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self.active.discard(ws)
        logging.info(f"WS disconnected. Total: {len(self.active)}")

    async def broadcast(self, message: str):
        """Send to all clients; silently remove dead connections.
        NOTE: Do NOT wrap ws.send_text in asyncio.wait_for — cancelling a
        mid-send WebSocket coroutine corrupts the frame and causes phantom
        client disconnects. Plain await + except is the correct pattern.
        """
        if not self.active:
            return
        async with self._lock:
            targets = set(self.active)
        dead = set()
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        if dead:
            async with self._lock:
                self.active -= dead

manager = ConnectionManager()

# Global state cache
_last_state = None
_is_running = False


def _serialize_state(state) -> dict:
    """Serialize PortfolioState to a JSON-safe dict, stripping DataFrames."""
    import pandas as pd

    def clean(obj):
        """Recursively clean an object to be JSON-safe."""
        if obj is None:
            return None
        if isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, (list, tuple)):
            return [clean(i) for i in obj]
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items()}
        if isinstance(obj, pd.DataFrame):
            return None   # Drop DataFrames entirely
        if isinstance(obj, pd.Series):
            return None
        if dataclasses.is_dataclass(obj):
            return clean(dataclasses.asdict(obj))
        # Fallback for other types (datetime, etc.)
        try:
            return str(obj)
        except Exception:
            return None

    try:
        # Manually build the output dict field by field
        out = {
            "run_id":               state.run_id,
            "started_at":           state.started_at,
            "completed_at":         state.completed_at,
            "total_portfolio_value":state.total_portfolio_value,
            "total_cost_basis":     state.total_cost_basis,
            "total_pnl":            state.total_pnl,
            "total_pnl_pct":        state.total_pnl_pct,
            "portfolio_var":        state.portfolio_var,
            "portfolio_sharpe":     state.portfolio_sharpe,
            "settings":             clean(state.settings),
            "holdings":             clean(state.holdings),
            "technical_signals":    clean(state.technical_signals),
            "fundamental_signals":  clean(state.fundamental_signals),
            "sentiment_signals":    clean(state.sentiment_signals),
            "macro_data":           clean(state.macro_data),
            "bull_theses":          clean(state.bull_theses),
            "bear_theses":          clean(state.bear_theses),
            "pattern_alerts":       clean(state.pattern_alerts),
            "risk_metrics":         clean(state.risk_metrics),
            "recommendations":      clean(state.recommendations),
            "scan_recommendations": clean(state.scan_recommendations),
            "preference_recommendations": clean(state.preference_recommendations),
            "smart_money_signals": clean(state.smart_money_signals),
            "agent_statuses":       clean(state.agent_statuses),
            "agent_logs": {
                k: v[-5:] for k, v in state.agent_logs.items()
            },
            # Slim price_data: only support/resistance levels, no DataFrames
            "price_data": {
                ticker: {
                    "support":    data.get("support"),
                    "resistance": data.get("resistance"),
                }
                for ticker, data in state.price_data.items()
                if isinstance(data, dict)
            },
        }
        return out
    except Exception as e:
        logging.error(f"Serialization error: {e}", exc_info=True)
        return {"error": str(e)}




@app.get("/")
async def root():
    """Serve the dashboard."""
    index_path = dashboard_path / "index.html"
    return FileResponse(str(index_path))


@app.get("/api/status")
async def get_status():
    """Get current system status."""
    return {
        "running": _is_running,
        "has_results": _last_state is not None,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/results")
async def get_results():
    """Get the latest analysis results."""
    if _last_state is None:
        return {"error": "No analysis run yet. POST /api/analyze to start."}
    return _serialize_state(_last_state)


@app.get("/api/health")
async def get_health():
    """Check status of all scraping data sources (no API keys needed)."""
    from core.data_engine import check_scraper_health
    status = check_scraper_health()
    all_ok = any(v == "OK" for v in status.values())
    return {
        "status": "OK" if all_ok else "DEGRADED",
        "sources": status,
        "note": "100% scraping — zero API keys required",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/portfolio")
async def get_portfolio():
    """Return current portfolio.json contents."""
    pf = Path(__file__).parent.parent / "data" / "portfolio.json"
    if not pf.exists():
        return {"error": "portfolio.json not found"}
    with open(pf) as f:
        return json.load(f)


@app.post("/api/portfolio")
async def save_portfolio(body: dict):
    """Save updated portfolio holdings to portfolio.json."""
    pf = Path(__file__).parent.parent / "data" / "portfolio.json"
    required = {"ticker", "name", "shares", "avg_buy_price", "sector"}
    for h in body.get("portfolio", []):
        missing = required - set(h.keys())
        if missing:
            return {"error": f"Missing fields in holding: {missing}"}
        if float(h["shares"]) <= 0:
            return {"error": f"Shares must be > 0 for {h['ticker']}"}
        if float(h["avg_buy_price"]) <= 0:
            return {"error": f"avg_buy_price must be > 0 for {h['ticker']}"}
    with open(pf, "w") as f:
        json.dump(body, f, indent=2)
    return {"status": "saved", "holdings": len(body.get("portfolio", [])), "timestamp": datetime.now().isoformat()}


@app.post("/api/strategy")
async def set_strategy(body: dict):
    """Set investment strategy preference (GROWTH/DIVIDEND/REIT/VALUE/MOMENTUM/ALL)."""
    valid = {"GROWTH", "DIVIDEND", "REIT", "VALUE", "MOMENTUM", "ALL"}
    strat = body.get("strategy", "ALL").upper()
    if strat not in valid:
        return {"error": f"Invalid strategy. Choose from: {valid}"}
    pf = Path(__file__).parent.parent / "data" / "portfolio.json"
    if pf.exists():
        with open(pf) as f:
            data = json.load(f)
        data.setdefault("settings", {})["strategy"] = strat
        with open(pf, "w") as f:
            json.dump(data, f, indent=2)
    return {"status": "strategy_set", "strategy": strat}


@app.post("/api/analyze")
async def run_analysis():
    """Trigger a fresh analysis run."""
    global _last_state, _is_running

    if _is_running:
        return {"error": "Analysis already running"}

    _is_running = True
    _broadcast_timestamps = {"last": 0.0}

    async def _run_and_broadcast():
        global _last_state, _is_running
        try:
            orchestrator = OrchestratorAgent(verbose=True)

            async def broadcaster(msg: str):
                """Throttled broadcaster — max 1 status_update per 200ms."""
                import time as _time
                try:
                    parsed = json.loads(msg)
                    if parsed.get("event") == "status_update":
                        now = _time.monotonic()
                        if now - _broadcast_timestamps["last"] < 0.2:
                            return
                        _broadcast_timestamps["last"] = now
                except Exception:
                    pass
                await manager.broadcast(msg)

            orchestrator.ws_broadcaster = broadcaster
            state = await orchestrator.run()
            _last_state = state

            final_state = _serialize_state(state)
            final_state.pop("agent_logs", None)
            await manager.broadcast(
                json.dumps({"event": "analysis_complete", "data": final_state})
            )
        except Exception as e:
            logging.error(f"Analysis error: {e}", exc_info=True)
            await manager.broadcast(json.dumps({
                "event": "error",
                "data":  {"message": str(e)},
            }))
        finally:
            _is_running = False

    asyncio.create_task(_run_and_broadcast())
    return {"status": "Analysis started", "message": "Watch WebSocket for live updates"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket — bulletproof with ping/pong heartbeat & graceful disconnect."""
    await manager.connect(ws)

    async def _heartbeat():
        """Send ping every 25s to keep alive through proxies/firewalls."""
        while True:
            try:
                await asyncio.sleep(25)
                await ws.send_text(json.dumps({"event": "ping"}))  # plain await — no wait_for
            except Exception:
                break

    heartbeat_task = asyncio.create_task(_heartbeat())
    try:
        if _last_state:
            await ws.send_text(json.dumps({
                "event": "initial_state",
                "data":  _serialize_state(_last_state),
            }))
        else:
            await ws.send_text(json.dumps({
                "event": "ready",
                "data":  {"message": "🟢 Connected to Antigravity Intelligence. POST /api/analyze to start."},
            }))

        # Keep-alive receive loop — wait_for on receive is safe (no send corruption)
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=60)
            except asyncio.TimeoutError:
                try:
                    await ws.send_text(json.dumps({"event": "ping"}))  # plain await
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logging.debug(f"WS error: {e}")
    finally:
        heartbeat_task.cancel()
        await manager.disconnect(ws)


if __name__ == "__main__":
    uvicorn.run("api.server:app", host="0.0.0.0", port=8080, reload=False, log_level="info")
