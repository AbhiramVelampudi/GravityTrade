import asyncio
import sys
sys.stdout.reconfigure(encoding='utf-8')

async def test():
    from agents.orchestrator import OrchestratorAgent
    orch = OrchestratorAgent(verbose=True)
    state = await orch.run()

    print("\n=== AGENT STATUS REPORT ===")
    all_ok = True
    for agent, status in state.agent_statuses.items():
        icon = "✅" if status == "DONE" else "❌" if status == "ERROR" else "⏳"
        print(f"  {icon}  {agent:<25} {status}")
        if status == "ERROR":
            all_ok = False

    print("\n=== RECOMMENDATIONS ===")
    for ticker, rec in state.recommendations.items():
        print(f"  {ticker}: {rec.action} @ {rec.confidence:.0%} | Stop ${rec.stop_loss:.2f} | Target ${rec.exit_target_1 or 0:.2f}")

    print("\n=== PORTFOLIO SUMMARY ===")
    print(f"  Total Value:  ${state.total_portfolio_value:,.2f}")
    print(f"  Total PnL:    {state.total_pnl_pct:+.2f}%")
    print(f"  Macro Signal: {state.macro_data.macro_signal if state.macro_data else 'N/A'}")

    errors = [a for a, s in state.agent_statuses.items() if s == "ERROR"]
    print(f"\n  ERRORS: {errors if errors else 'NONE — ALL GREEN'}")
    print(f"  PIPELINE: {'FAILED' if errors else 'SUCCESS'}")

asyncio.run(test())
