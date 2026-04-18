"""
Agent 9: Bear Agent
Constructs the strongest possible bearish thesis — plays devil's advocate.
"""
import asyncio
from agents.base_agent import BaseAgent
from core.state import BullBearThesis


class BearAgent(BaseAgent):
    name = "BearAgent"
    description = "Devil's advocate — builds the strongest bear case for every position."

    def _build_bear_points(self, ticker: str) -> list:
        points = []
        ta = self.state.technical_signals.get(ticker)
        fund = self.state.fundamental_signals.get(ticker)
        sent = self.state.sentiment_signals.get(ticker)
        macro = self.state.macro_data
        holding = next((h for h in self.state.holdings if h.ticker == ticker), None)

        # Technical bear points
        if ta:
            if ta.rsi_14 and ta.rsi_14 > 65:
                points.append(f"RSI at {ta.rsi_14:.1f} — overbought, mean reversion risk high")
            if ta.macd and ta.macd_signal and ta.macd < ta.macd_signal:
                points.append("MACD death cross forming — bearish momentum accelerating")
            if ta.ta_score and ta.ta_score < 40:
                points.append(f"TA composite score {ta.ta_score:.0f}/100 — technically broken")
            if ta.ema_50 and ta.ema_200 and ta.ema_50 < ta.ema_200:
                points.append("EMA 50 below EMA 200 — death cross in effect, downtrend confirmed")
            if ta.bb_upper and holding and holding.current_price:
                if holding.current_price > ta.bb_upper * 0.98:
                    points.append("Price touching upper Bollinger Band — overextended, reversal risk")
            if ta.volume_ratio and ta.volume_ratio < 0.7:
                points.append(f"Volume at {ta.volume_ratio:.1f}x average — weak buying interest")

        # Fundamental bear points
        if fund:
            if fund.pe_ratio and fund.pe_ratio > 40:
                points.append(f"P/E ratio {fund.pe_ratio:.1f}x — premium valuation leaves no room for error")
            if fund.revenue_growth_yoy and fund.revenue_growth_yoy < 0.05:
                points.append(f"Revenue growth decelerating to {fund.revenue_growth_yoy*100:.1f}% — growth story weakening")
            if fund.debt_to_equity and fund.debt_to_equity > 1.5:
                points.append(f"Debt/equity {fund.debt_to_equity:.1f} — over-leveraged, rising rate risk")
            if fund.analyst_target and holding and holding.current_price:
                if holding.current_price > fund.analyst_target * 1.05:
                    points.append(f"Trading ABOVE analyst consensus target ${fund.analyst_target:.2f} — priced for perfection")
            if fund.analyst_rating in ("underperform", "sell"):
                points.append(f"Analyst rating: {fund.analyst_rating.upper()} — institutional selling pressure")
            if fund.profit_margin and fund.profit_margin < 0.05:
                points.append(f"Thin profit margin {fund.profit_margin*100:.1f}% — vulnerable to cost shocks")

        # Sentiment bear points
        if sent:
            if sent.sentiment_score is not None and sent.sentiment_score < -0.15:
                points.append(f"News sentiment negative ({sent.sentiment_score:+.2f}) — press coverage turning hostile")
            if sent.news_count < 3:
                points.append("Low news coverage — potential hidden risks not yet priced")

        # Macro bear points
        if macro:
            if macro.macro_signal in ("RISK_OFF", "CAUTIOUSLY_BEARISH"):
                points.append(f"Macro: {macro.macro_signal} — unfavorable macro regime for equities")
            if macro.vix and macro.vix > 25:
                points.append(f"VIX at {macro.vix:.1f} — elevated fear, risk of forced selling")
            if macro.yield_curve_spread and macro.yield_curve_spread < -0.3:
                points.append(f"Yield curve inverted by {abs(macro.yield_curve_spread):.2f}% — historical recession signal")
            if macro.yield_10y and macro.yield_10y > 4.5:
                points.append(f"10Y Treasury at {macro.yield_10y:.2f}% — high risk-free rate compresses equity valuations")

        # Holding-specific risk
        if holding:
            if holding.unrealized_pnl_pct and holding.unrealized_pnl_pct > 50:
                points.append(f"Up {holding.unrealized_pnl_pct:.0f}% from cost basis — profit-taking pressure likely")

        return points if points else ["No significant bear signals at this time — position appears safe"]

    def _estimate_bear_target(self, ticker: str) -> float:
        holding = next((h for h in self.state.holdings if h.ticker == ticker), None)
        ta = self.state.technical_signals.get(ticker)
        
        current = holding.current_price if holding else None
        if not current:
            return 0.0
        
        # Bear target: 10-25% downside
        ta_score = (ta.ta_score or 50) if ta else 50
        downside_pct = 0.10 + ((100 - ta_score) / 100 * 0.20)
        return round(current * (1 - downside_pct), 2)

    async def run(self):
        self.log(f"🐻 Building bear theses for {len(self.state.holdings)} holdings...")
        
        for holding in self.state.holdings:
            ticker = holding.ticker
            
            points = self._build_bear_points(ticker)
            target = self._estimate_bear_target(ticker)
            
            # Bear confidence is inverse of bull signals
            ta = self.state.technical_signals.get(ticker)
            fund = self.state.fundamental_signals.get(ticker)
            sent = self.state.sentiment_signals.get(ticker)
            
            bear_scores = []
            if ta and ta.ta_score: bear_scores.append(1.0 - ta.ta_score / 100)
            if fund and fund.fundamental_score: bear_scores.append(1.0 - fund.fundamental_score / 100)
            if sent and sent.sentiment_score is not None:
                bear_scores.append((1.0 - sent.sentiment_score) / 2)
            
            confidence = sum(bear_scores) / len(bear_scores) if bear_scores else 0.3
            confidence = round(min(0.90, max(0.05, confidence)), 3)
            
            thesis = BullBearThesis(
                ticker=ticker,
                side="bear",
                confidence=confidence,
                key_points=points,
                price_target=target,
                timeframe="1-3 months",
                risks=["Short squeeze risk", "Positive earnings surprise", "M&A / buyout premium"],
            )
            
            self.state.bear_theses[ticker] = thesis
            self.log(
                f"  🐻 {ticker}: Confidence={confidence:.0%} | "
                f"Bear Target=${target:.2f} | Points={len(points)}"
            )
        
        self.log("✅ Bear theses complete.")
