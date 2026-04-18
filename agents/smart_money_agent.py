"""
Agent 16: Smart Money Agent
Uses SEC EDGAR insider trades, options P/C ratio, short squeeze setups,
earnings calendar, and sector rotation to generate institutional-grade signals.
This is the edge that hedge funds pay millions for — we scrape it free.
"""
import asyncio
from agents.base_agent import BaseAgent


class SmartMoneyAgent(BaseAgent):
    name = "SmartMoney"
    description = (
        "SEC EDGAR insider tracking + options flow + short squeeze detector + "
        "sector rotation. Finds where smart money is moving BEFORE it's on the news."
    )

    async def run(self):
        from core.signal_engine import get_smart_money_score

        self.log("🧠 [CITADEL INTELLIGENCE MODE] Scanning smart money signals...")
        self.log("   Sources: SEC Form 4 (insiders) | Options P/C | Short Interest | Sector ETFs")

        if not self.state.holdings:
            self.log("⚠️  No holdings to analyze")
            return

        all_scores = {}
        for holding in self.state.holdings:
            ticker = holding.ticker
            sector = holding.sector or "Technology"
            try:
                self.log(f"  🔍 {ticker}: fetching insider + options + short data...")
                result = get_smart_money_score(ticker, sector)
                all_scores[ticker] = result

                insider  = result["insider"]
                options  = result["options"]
                short    = result["short"]
                earnings = result["earnings"]

                self.log(
                    f"  📊 {ticker}: SmartScore={result['smart_score']:.0f} | "
                    f"Insider={insider['insider_signal']} ({insider['insider_buys']}B/{insider['insider_sells']}S) | "
                    f"Options={options['options_signal']} P/C={options['pc_ratio']} | "
                    f"Short={short.get('short_float_pct','?')}% | "
                    f"Earnings={earnings['earnings_signal']}"
                )
            except Exception as e:
                self.log(f"  ⚠️  {ticker}: {e}")
                continue

        # Store in state
        self.state.smart_money_signals = all_scores

        # Log top signals
        sorted_tickers = sorted(all_scores.items(), key=lambda x: x[1]["smart_score"], reverse=True)
        self.log("\n🏆 SMART MONEY RANKINGS:")
        for tk, data in sorted_tickers:
            self.log(f"   {tk}: {data['smart_signal']} @ {data['smart_score']:.0f}/100")

        self.log(f"✅ Smart money scan complete — {len(all_scores)} positions analyzed")
