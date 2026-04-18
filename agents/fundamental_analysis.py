"""
Agent 5: Fundamental Analysis Agent
P/E, EPS growth, debt/equity, revenue trends, analyst targets, composite score.
"""
import asyncio
from agents.base_agent import BaseAgent
from core.state import FundamentalSignals


class FundamentalAnalysisAgent(BaseAgent):
    name = "FundamentalAnalysis"
    description = "Goldman Sachs senior analyst & Morgan Stanley VP. Evaluates P/E, growth, and DCF metrics."

    def _score_pe(self, pe: float, sector: str) -> float:
        """Score P/E vs sector norms."""
        if pe is None or pe <= 0: return 50.0
        # Tech sector higher P/E is acceptable
        sector_pe_norm = {
            "Technology": 35, "Communication Services": 30,
            "Consumer Discretionary": 28, "Healthcare": 25,
            "Financials": 18, "Energy": 15, "Industrials": 22,
            "Materials": 20, "Utilities": 20, "Consumer Staples": 22,
            "Real Estate": 30,
        }
        norm = sector_pe_norm.get(sector, 25)
        ratio = pe / norm
        if ratio < 0.7:   return 85.0   # undervalued
        if ratio < 0.9:   return 70.0
        if ratio < 1.1:   return 55.0
        if ratio < 1.3:   return 40.0
        if ratio < 1.6:   return 30.0
        return 15.0  # very expensive

    def _score_growth(self, growth: float) -> float:
        """Score revenue/earnings growth."""
        if growth is None: return 50.0
        pct = growth * 100
        if pct > 30:   return 90.0
        if pct > 20:   return 80.0
        if pct > 10:   return 65.0
        if pct > 5:    return 55.0
        if pct > 0:    return 45.0
        if pct > -5:   return 35.0
        return 15.0

    def _score_analyst(self, current: float, target: float, rating: str) -> float:
        """Score analyst consensus vs current price."""
        score = 50.0
        if current and target and current > 0:
            upside = ((target - current) / current) * 100
            if upside > 30:    score = 90.0
            elif upside > 20:  score = 80.0
            elif upside > 10:  score = 65.0
            elif upside > 0:   score = 55.0
            elif upside > -10: score = 40.0
            else:              score = 25.0
        
        rating_boost = {
            "strong_buy": 10, "buy": 5, "hold": 0,
            "underperform": -5, "sell": -10
        }
        score += rating_boost.get(rating or "", 0)
        return max(0, min(100, score))

    def _score_debt(self, de_ratio: float) -> float:
        """Lower debt = higher score."""
        if de_ratio is None: return 55.0
        if de_ratio < 0.3:   return 90.0
        if de_ratio < 0.6:   return 75.0
        if de_ratio < 1.0:   return 55.0
        if de_ratio < 1.5:   return 40.0
        return 20.0

    def _signal_from_score(self, score: float) -> str:
        if score >= 70: return "STRONG_BUY"
        if score >= 60: return "BUY"
        if score >= 45: return "HOLD"
        if score >= 30: return "UNDERPERFORM"
        return "SELL"

    async def run(self):
        self.log(f"🏦 [GOLDMAN SACHS / MORGAN STANLEY MODE] Running fundamental screening on {len(self.state.holdings)} holdings...")
        
        for holding in self.state.holdings:
            ticker = holding.ticker
            self.log(f"  ↳ Fetching fundamentals for {ticker}...")
            
            raw = self.use_tool("get_fundamentals", ticker=ticker)
            
            current_price = holding.current_price or holding.avg_buy_price
            analyst_target = raw.get("analyst_target")
            analyst_rating = raw.get("analyst_rating")
            
            # Sub-scores
            s_pe     = self._score_pe(raw.get("pe_ratio"), holding.sector)
            s_growth = self._score_growth(raw.get("revenue_growth_yoy"))
            s_earn   = self._score_growth(raw.get("earnings_growth_yoy"))
            s_analyst = self._score_analyst(current_price, analyst_target, analyst_rating)
            s_debt   = self._score_debt(raw.get("debt_to_equity"))
            
            # Composite score
            fund_score = (
                s_pe      * 0.20 +
                s_growth  * 0.25 +
                s_earn    * 0.25 +
                s_analyst * 0.20 +
                s_debt    * 0.10
            )
            fund_score = max(0.0, min(100.0, fund_score))
            
            # Upside to analyst target
            upside_pct = None
            if analyst_target and current_price:
                upside_pct = round(((analyst_target - current_price) / current_price) * 100, 1)
            
            signals = FundamentalSignals(
                ticker=ticker,
                pe_ratio=raw.get("pe_ratio"),
                forward_pe=raw.get("forward_pe"),
                peg_ratio=raw.get("peg_ratio"),
                price_to_book=raw.get("price_to_book"),
                price_to_sales=raw.get("price_to_sales"),
                debt_to_equity=raw.get("debt_to_equity"),
                current_ratio=raw.get("current_ratio"),
                roe=raw.get("roe"),
                revenue_growth_yoy=raw.get("revenue_growth_yoy"),
                earnings_growth_yoy=raw.get("earnings_growth_yoy"),
                profit_margin=raw.get("profit_margin"),
                free_cash_flow=raw.get("free_cash_flow"),
                market_cap=raw.get("market_cap"),
                analyst_target=analyst_target,
                analyst_rating=analyst_rating,
                fundamental_score=round(fund_score, 1),
                fundamental_signal=self._signal_from_score(fund_score),
            )
            
            self.state.fundamental_signals[ticker] = signals
            
            rev_g = raw.get('revenue_growth_yoy')
            rev_str = f"{rev_g*100:.1f}%" if rev_g else 'N/A'
            tgt_str = f"${analyst_target:.2f}" if analyst_target else 'N/A'
            up_str = (f"+{upside_pct}%" if upside_pct and upside_pct > 0
                      else f"{upside_pct}%" if upside_pct else 'N/A')
            self.log(
                f"  {ticker}: P/E={raw.get('pe_ratio','N/A')} | "
                f"Rev Growth={rev_str} | Analyst Target={tgt_str} ({up_str}) | "
                f"Score={fund_score:.0f}/100 | Signal={signals.fundamental_signal}"
            )
        
        self.log("✅ Fundamental analysis complete.")
