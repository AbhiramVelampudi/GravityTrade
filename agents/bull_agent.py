"""
Agent 8: Bull Agent
Constructs the strongest possible bullish thesis for each holding.
Uses TA, fundamentals, sentiment, and macro signals.
"""
import asyncio
from agents.base_agent import BaseAgent
from core.state import BullBearThesis


class BullAgent(BaseAgent):
    name = "BullAgent"
    description = "Bain & Company strategy analyst constructing the competitive bull case and upside catalysts."

    def _build_bull_points(self, ticker: str) -> list:
        points = []
        ta = self.state.technical_signals.get(ticker)
        fund = self.state.fundamental_signals.get(ticker)
        sent = self.state.sentiment_signals.get(ticker)
        macro = self.state.macro_data

        # Technical bull points
        if ta:
            if ta.rsi_14 and ta.rsi_14 < 40:
                points.append(f"RSI at {ta.rsi_14:.1f} — oversold territory, strong bounce potential")
            if ta.macd and ta.macd_signal and ta.macd > ta.macd_signal:
                points.append("MACD bullish crossover — momentum is turning positive")
            if ta.ta_score and ta.ta_score >= 65:
                points.append(f"Composite TA score {ta.ta_score:.0f}/100 — technically strong")
            if ta.ema_50 and ta.ema_200 and ta.ema_50 > ta.ema_200:
                points.append("EMA 50 above EMA 200 — confirmed uptrend structure")
            if ta.volume_ratio and ta.volume_ratio > 1.3:
                points.append(f"Volume {ta.volume_ratio:.1f}x above 20-day average — institutional buying pressure")

        # Fundamental bull points
        if fund:
            if fund.revenue_growth_yoy and fund.revenue_growth_yoy > 0.10:
                points.append(f"Revenue growing {fund.revenue_growth_yoy*100:.1f}% YoY — strong business momentum")
            if fund.earnings_growth_yoy and fund.earnings_growth_yoy > 0.10:
                points.append(f"Earnings growth {fund.earnings_growth_yoy*100:.1f}% YoY — profitability accelerating")
            if fund.analyst_target and fund.analyst_rating in ("buy", "strong_buy"):
                points.append(f"Analyst consensus: {fund.analyst_rating.upper()} — Wall Street confidence high")
            if fund.roe and fund.roe > 0.15:
                points.append(f"ROE of {fund.roe*100:.1f}% — excellent capital efficiency")
            if fund.profit_margin and fund.profit_margin > 0.15:
                points.append(f"Profit margin {fund.profit_margin*100:.1f}% — wide economic moat")
            if fund.free_cash_flow and fund.free_cash_flow > 0:
                fcf_b = fund.free_cash_flow / 1e9
                points.append(f"Positive free cash flow of ${fcf_b:.1f}B — strong balance sheet")

        # Sentiment bull points
        if sent:
            if sent.sentiment_score and sent.sentiment_score > 0.2:
                points.append(f"News sentiment strongly positive ({sent.sentiment_score:+.2f}) — market tailwind")
            elif sent.sentiment_score and sent.sentiment_score > 0:
                points.append(f"News sentiment moderately bullish — favorable press coverage")

        # Macro bull points
        if macro:
            if macro.macro_signal in ("RISK_ON", "CAUTIOUSLY_BULLISH"):
                points.append(f"Macro environment: {macro.macro_signal} — equity-friendly conditions")
            if macro.vix and macro.vix < 20:
                points.append(f"VIX at {macro.vix:.1f} — low volatility regime favors equity longs")
            if macro.yield_curve_spread and macro.yield_curve_spread > 0:
                points.append("Yield curve positive — no recession signal in bond market")

        return points if points else ["No strong bull signals at this time — holding cautiously"]

    def _estimate_bull_target(self, ticker: str) -> float:
        holding = next((h for h in self.state.holdings if h.ticker == ticker), None)
        fund = self.state.fundamental_signals.get(ticker)
        ta = self.state.technical_signals.get(ticker)
        
        current = holding.current_price if holding else None
        if not current:
            return 0.0
        
        # Use analyst target or estimate 15-25% upside
        if fund and fund.analyst_target:
            return round(fund.analyst_target, 2)
        
        # Estimate from TA score
        score = (ta.ta_score or 50) / 100 if ta else 0.5
        upside_pct = 0.10 + (score * 0.20)  # 10-30% upside
        return round(current * (1 + upside_pct), 2)

    async def run(self):
        self.log(f"🐂 [BAIN & COMPANY MODE] Building competitive strategy bull theses for {len(self.state.holdings)} holdings...")
        
        for holding in self.state.holdings:
            ticker = holding.ticker
            
            points = self._build_bull_points(ticker)
            target = self._estimate_bull_target(ticker)
            
            # Calculate overall bull confidence
            ta = self.state.technical_signals.get(ticker)
            fund = self.state.fundamental_signals.get(ticker)
            sent = self.state.sentiment_signals.get(ticker)
            
            scores = []
            if ta and ta.ta_score: scores.append(ta.ta_score / 100)
            if fund and fund.fundamental_score: scores.append(fund.fundamental_score / 100)
            if sent and sent.sentiment_score is not None: scores.append((sent.sentiment_score + 1) / 2)
            
            confidence = sum(scores) / len(scores) if scores else 0.5
            confidence = round(min(0.95, max(0.1, confidence)), 3)
            
            current = holding.current_price or 0
            if current > 0 and target > 0:
                upside = ((target - current) / current) * 100
                timeframe = "1-3 months" if upside < 15 else ("3-6 months" if upside < 30 else "6-12 months")
            else:
                timeframe = "3-6 months"
            
            thesis = BullBearThesis(
                ticker=ticker,
                side="bull",
                confidence=confidence,
                key_points=points,
                price_target=target,
                timeframe=timeframe,
                risks=["Broader market correction", "Earnings miss risk", "Interest rate headwinds"],
            )
            
            self.state.bull_theses[ticker] = thesis
            self.log(
                f"  🐂 {ticker}: Confidence={confidence:.0%} | "
                f"Target=${target:.2f} | Points={len(points)}"
            )
        
        self.log("✅ Bull theses complete.")
