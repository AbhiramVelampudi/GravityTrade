"""
run.py — Entry point for Antigravity Stock Intelligence System
Usage:
  python run.py          → Start the full server + dashboard
  python run.py --cli    → Run analysis in CLI-only mode (no web server)
"""
import sys
import os
import asyncio
import logging

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)-20s] %(message)s",
    datefmt="%H:%M:%S"
)


def run_server():
    """Start the FastAPI web server."""
    import uvicorn
    print("\n" + "="*60)
    print("  [*]  ANTIGRAVITY STOCK INTELLIGENCE SYSTEM")
    print("  [13] Agent MCP Portfolio Analyzer")
    print("="*60)
    print(f"\n  Dashboard: http://localhost:8080")
    print(f"  API:       http://localhost:8080/api")
    print(f"  WebSocket: ws://localhost:8080/ws")
    print(f"\n  --> Open http://localhost:8080 in your browser")
    print(f"  --> Click [Run Analysis] to start all 13 agents")
    print("\n" + "="*60 + "\n")
    uvicorn.run(
        "api.server:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
        log_level="warning",
    )


async def run_cli():
    """Run analysis pipeline in CLI mode."""
    from agents.orchestrator import OrchestratorAgent
    import json

    print("\n" + "="*60)
    print("  ⚡  ANTIGRAVITY — CLI MODE")
    print("="*60 + "\n")

    orchestrator = OrchestratorAgent(verbose=True)
    state = await orchestrator.run()

    print("\n" + "="*60)
    print("  🏆  FINAL RECOMMENDATIONS")
    print("="*60)

    emoji_map = {"BUY": "🟢", "ADD": "🔵", "HOLD": "⚪",
                 "WATCH": "🟡", "TRIM": "🟠", "SELL": "🔴"}

    for ticker, rec in state.recommendations.items():
        e = emoji_map.get(rec.action, "⚪")
        print(f"\n  {e} {ticker}: {rec.action}")
        print(f"     Confidence: {rec.confidence:.0%}")
        print(f"     Entry:      {rec.entry_window_start} → {rec.entry_window_end}")
        print(f"     Entry Zone: ${rec.entry_price_low:.2f} – ${rec.entry_price_high:.2f}")
        print(f"     Target:     ${rec.exit_target_1:.2f if rec.exit_target_1 else '—'}")
        print(f"     Stop Loss:  ${rec.stop_loss:.2f if rec.stop_loss else '—'}")
        print(f"     Urgency:    {rec.urgency}")
        print(f"     Alloc:      {rec.allocation_pct:.0f}% of portfolio")

    print(f"\n  📊 Portfolio Value: ${state.total_portfolio_value:,.2f}")
    print(f"  💰 Total P&L:      {'+' if (state.total_pnl or 0) >= 0 else ''}"
          f"${state.total_pnl:,.2f} ({'+' if (state.total_pnl_pct or 0) >= 0 else ''}{state.total_pnl_pct:.2f}%)")

    if state.macro_data:
        m = state.macro_data
        print(f"\n  🌍 Macro: {m.macro_signal} | VIX: {m.vix:.1f if m.vix else 'N/A'} | "
              f"10Y: {m.yield_10y:.2f if m.yield_10y else 'N/A'}%")

    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    if "--cli" in sys.argv:
        asyncio.run(run_cli())
    else:
        run_server()
