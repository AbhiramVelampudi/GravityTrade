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

# Per-connection wrapper with a dedicated sender task
class WSConn:
    """Each WebSocket gets its own queue + sender coroutine.
    This is the ONLY correct way to send from multiple coroutines to the same WS.
    Concurrent ws.send_text() calls corrupt the WebSocket frame stream.
    """
    _STOP = object()  # sentinel

    def __init__(self, ws: WebSocket):
        self.ws   = ws
        self.q    = asyncio.Queue(maxsize=256)
        self.task = asyncio.ensure_future(self._drain())

    async def _drain(self):
        while True:
            msg = await self.q.get()
            if msg is self._STOP:
                break
            try:
                await self.ws.send_text(msg)
            except Exception:
                break  # connection gone — stop draining

    def enqueue(self, msg: str):
        try:
            self.q.put_nowait(msg)
        except asyncio.QueueFull:
            pass  # drop if backlogged (never block the caller)

    async def stop(self):
        try:
            self.q.put_nowait(self._STOP)
        except asyncio.QueueFull:
            pass
        self.task.cancel()


class ConnectionManager:
    def __init__(self):
        self._conns: dict = {}   # WebSocket → WSConn
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        conn = WSConn(ws)
        async with self._lock:
            self._conns[ws] = conn
        logging.info(f"WS connected. Total: {len(self._conns)}")
        return conn

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            conn = self._conns.pop(ws, None)
        if conn:
            await conn.stop()
        logging.info(f"WS disconnected. Total: {len(self._conns)}")

    async def broadcast(self, message: str):
        """Enqueue message for every connected client. Never blocks, never corrupts."""
        async with self._lock:
            conns = list(self._conns.values())
        for conn in conns:
            conn.enqueue(message)


manager = ConnectionManager()

# Global state cache
_last_state = None
_is_running = False


def _serialize_state(state) -> dict:
    """Serialize PortfolioState to a JSON-safe dict, stripping DataFrames."""
    import pandas as pd

    import math

    def clean(obj):
        """Recursively clean an object to be JSON-safe."""
        if obj is None:
            return None
        if isinstance(obj, bool):        # bool before int (bool is subclass of int)
            return obj
        if isinstance(obj, int):
            return obj
        if isinstance(obj, float):
            # inf/nan crash json.dumps — sanitize them
            if math.isnan(obj) or math.isinf(obj):
                return None
            return obj
        if isinstance(obj, str):
            return obj
        if isinstance(obj, (list, tuple)):
            return [clean(i) for i in obj]
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items()}
        if isinstance(obj, pd.DataFrame):
            return None
        if isinstance(obj, pd.Series):
            return None
        if dataclasses.is_dataclass(obj):
            return clean(dataclasses.asdict(obj))
        # numpy scalar types
        try:
            import numpy as np
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                v = float(obj)
                return None if (math.isnan(v) or math.isinf(v)) else v
            if isinstance(obj, np.ndarray):
                return clean(obj.tolist())
        except (ImportError, Exception):
            pass
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
            "total_portfolio_value":clean(state.total_portfolio_value),
            "total_cost_basis":     clean(state.total_cost_basis),
            "total_pnl":            clean(state.total_pnl),
            "total_pnl_pct":        clean(state.total_pnl_pct),
            "portfolio_var":        clean(state.portfolio_var),
            "portfolio_sharpe":     clean(state.portfolio_sharpe),
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
            "smart_money_signals":  clean(state.smart_money_signals),
            "agent_statuses":       clean(state.agent_statuses),
            "agent_logs": {
                k: v[-5:] for k, v in state.agent_logs.items()
            },
            # Slim price_data: only support/resistance levels, no DataFrames
            "price_data": {
                ticker: {
                    "support":    clean(data.get("support")),
                    "resistance": clean(data.get("resistance")),
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
    required = {"ticker", "shares", "avg_buy_price"}
    
    holdings = []
    for h in body.get("portfolio", []):
        missing = required - set(h.keys())
        if missing:
            return {"error": f"Missing fields in holding: {missing}"}
        if float(h["shares"]) <= 0:
            return {"error": f"Shares must be > 0 for {h['ticker']}"}
        if float(h["avg_buy_price"]) <= 0:
            return {"error": f"avg_buy_price must be > 0 for {h['ticker']}"}
            
        ticker = h["ticker"]
        name = h.get("name")
        sector = h.get("sector")
        
        if not name or not sector or name == "New Stock":
            try:
                def fetch_info(t):
                    import yfinance as yf
                    return yf.Ticker(t).info
                info = await asyncio.to_thread(fetch_info, ticker)
                name = info.get("shortName") or info.get("longName") or ticker
                sector = info.get("sector") or "Unknown"
            except Exception:
                name = ticker
                sector = "Unknown"
                
        holdings.append({
            "ticker": ticker,
            "name": name,
            "shares": float(h["shares"]),
            "avg_buy_price": float(h["avg_buy_price"]),
            "sector": sector,
            "currency": h.get("currency", "USD")
        })
        
    body["portfolio"] = holdings
    with open(pf, "w") as f:
        json.dump(body, f, indent=2)
    return {"status": "saved", "holdings": len(holdings), "timestamp": datetime.now().isoformat()}


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
                """Throttled broadcaster — max 1 status_update per 200ms.
                MUST NOT raise — an exception here kills the entire pipeline."""
                try:
                    import time as _time
                    parsed = json.loads(msg)
                    if parsed.get("event") == "status_update":
                        now = _time.monotonic()
                        if now - _broadcast_timestamps["last"] < 0.2:
                            return
                        _broadcast_timestamps["last"] = now
                except Exception:
                    pass
                try:
                    await manager.broadcast(msg)
                except Exception as bcast_err:
                    logging.debug(f"Broadcast error (non-fatal): {bcast_err}")

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
    """WebSocket — queue-based sends, no concurrent write corruption."""
    conn = await manager.connect(ws)

    # Heartbeat: enqueue pings via queue (never direct ws.send_text from here)
    async def _heartbeat():
        while True:
            try:
                await asyncio.sleep(25)
                conn.enqueue(json.dumps({"event": "ping"}))
            except Exception:
                break

    heartbeat_task = asyncio.create_task(_heartbeat())
    try:
        # Initial state goes through the queue too — stays serialized
        if _last_state:
            conn.enqueue(json.dumps({
                "event": "initial_state",
                "data":  _serialize_state(_last_state),
            }))
        else:
            conn.enqueue(json.dumps({
                "event": "ready",
                "data":  {"message": "🟢 Connected to Antigravity Intelligence. POST /api/analyze to start."},
            }))

        # Pure receive loop — we only receive here, never send directly
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=90)
            except asyncio.TimeoutError:
                conn.enqueue(json.dumps({"event": "ping"}))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logging.debug(f"WS error: {e}")
    finally:
        heartbeat_task.cancel()
        await manager.disconnect(ws)


if __name__ == "__main__":
    uvicorn.run("api.server:app", host="0.0.0.0", port=8080, reload=False,
                log_level="info", ws_ping_interval=None, ws_ping_timeout=None)
