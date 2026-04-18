"""
Agent 12: Time-Precision Advisor
Determines the OPTIMAL entry and exit windows based on all signals combined.
Uses earnings calendar, seasonality, TA confluence, and options expiry patterns.
"""
import asyncio
from datetime import datetime, timedelta
from typing import Tuple, Optional
from agents.base_agent import BaseAgent


# Historical seasonality: months where each sector historically outperforms (simplified)
SECTOR_SEASONALITY = {
    "Technology":              [1, 2, 4, 10, 11],   # Q4 + Jan effect strong
    "Consumer Discretionary":  [3, 4, 10, 11, 12],
    "Communication Services":  [1, 4, 7, 10],
    "Healthcare":              [1, 2, 9, 10],
    "Financials":              [3, 4, 6, 9],
    "Energy":                  [1, 2, 5, 6, 11],
    "Industrials":             [3, 4, 10, 11],
    "Materials":               [2, 3, 9, 10],
    "Real Estate":             [1, 2, 11, 12],
    "Utilities":               [1, 11, 12],
    "Consumer Staples":        [1, 9, 10],
}

# Day-of-week effect: historically Monday/Tuesday show weakness, Fri tends positive
DOW_BIAS = {0: -0.5, 1: -0.2, 2: 0.1, 3: 0.2, 4: 0.3}  # Mon=0 ... Fri=4

# Options expiration: third Friday of each month — avoid entry 2 days before
def get_next_opex(from_date: datetime) -> datetime:
    """Get the next monthly options expiry (3rd Friday)."""
    year, month = from_date.year, from_date.month
    first_day = datetime(year, month, 1)
    fridays = [first_day + timedelta(days=i)
               for i in range(31)
               if (first_day + timedelta(days=i)).month == month
               and (first_day + timedelta(days=i)).weekday() == 4]
    opex = fridays[2] if len(fridays) >= 3 else fridays[-1]
    if opex < from_date:
        # Move to next month
        if month == 12:
            return get_next_opex(datetime(year + 1, 1, 1))
        return get_next_opex(datetime(year, month + 1, 1))
    return opex


class TimePrecisionAdvisorAgent(BaseAgent):
    name = "TimePrecisionAdvisor"
    description = "Pinpoints optimal entry/exit windows using seasonality, earnings, and confluence."

    def _get_seasonality_score(self, sector: str, current_month: int) -> float:
        """Score how favorable the current month is for this sector."""
        strong_months = SECTOR_SEASONALITY.get(sector, [])
        if current_month in strong_months:
            return 1.0
        # Check adjacent months
        adj = [m % 12 + 1 for m in [current_month - 2, current_month - 1]]
        if any(m in strong_months for m in adj):
            return 0.5
        return 0.0

    def _compute_entry_urgency(
        self, ticker: str, sector: str
    ) -> Tuple[str, str, str]:
        """
        Compute optimal entry window.
        Returns: (window_start, window_end, urgency)
        """
        now = datetime.now()
        ta = self.state.technical_signals.get(ticker)
        fund = self.state.fundamental_signals.get(ticker)
        risk = self.state.risk_metrics.get(ticker)
        sent = self.state.sentiment_signals.get(ticker)
        macro = self.state.macro_data
        
        # Start from next trading day
        entry_start = now + timedelta(days=1)
        # Skip weekends
        while entry_start.weekday() >= 5:
            entry_start += timedelta(days=1)
        
        # Base window: 3 trading days
        entry_end = entry_start + timedelta(days=4)
        while entry_end.weekday() >= 5:
            entry_end += timedelta(days=1)
        
        urgency_score = 0
        
        # TA confluence signals
        if ta:
            if ta.rsi_14 and ta.rsi_14 < 35:       urgency_score += 3  # oversold
            if ta.macd_histogram and ta.macd_histogram > 0: urgency_score += 2
            if ta.ta_score and ta.ta_score >= 65:   urgency_score += 2
            if ta.volume_ratio and ta.volume_ratio > 1.5: urgency_score += 1
        
        # Fundamental: if near earnings, tighten or delay
        if fund:
            if fund.analyst_rating in ("strong_buy", "buy"):
                urgency_score += 2
        
        # Seasonality
        month_score = self._get_seasonality_score(sector, now.month)
        urgency_score += int(month_score * 2)
        
        # Macro
        if macro:
            if macro.macro_signal in ("RISK_ON", "CAUTIOUSLY_BULLISH"):
                urgency_score += 2
            elif macro.macro_signal == "RISK_OFF":
                urgency_score -= 3
        
        # Sentiment momentum
        if sent and sent.sentiment_score and sent.sentiment_score > 0.2:
            urgency_score += 1
        
        # Options expiry proximity (avoid 2 days before)
        opex = get_next_opex(now)
        days_to_opex = (opex - now).days
        if 0 < days_to_opex < 3:
            # Push entry past expiry
            entry_start = opex + timedelta(days=1)
            entry_end = entry_start + timedelta(days=3)
        
        # Urgency classification
        if urgency_score >= 10:    urgency = "CRITICAL"   # Enter NOW
        elif urgency_score >= 7:   urgency = "HIGH"       # Enter this week
        elif urgency_score >= 4:   urgency = "MEDIUM"     # Enter within 2 weeks
        else:                      urgency = "LOW"        # No rush / wait for dip
        
        return (
            entry_start.strftime("%Y-%m-%d"),
            entry_end.strftime("%Y-%m-%d"),
            urgency,
        )

    def _compute_exit_window(
        self, ticker: str, entry_start: str, current_price: float, target_price: float
    ) -> Tuple[Optional[str], Optional[str]]:
        """Estimate when the target price might be reached."""
        ta = self.state.technical_signals.get(ticker)
        
        if not current_price or not target_price or target_price <= current_price:
            return (None, None)
        
        upside = (target_price - current_price) / current_price
        
        # Estimate based on trend strength
        daily_drift = 0.003  # default 0.3%/day
        if ta and ta.ta_score:
            daily_drift = 0.001 + (ta.ta_score / 100) * 0.006
        
        est_days = int(upside / daily_drift) if daily_drift > 0 else 90
        est_days = max(5, min(365, est_days))
        
        entry_dt = datetime.strptime(entry_start, "%Y-%m-%d")
        exit_start = entry_dt + timedelta(days=est_days - 10)
        exit_end   = entry_dt + timedelta(days=est_days + 15)
        
        return (exit_start.strftime("%Y-%m-%d"), exit_end.strftime("%Y-%m-%d"))

    async def run(self):
        self.log(f"⏰ Computing time-precision windows for {len(self.state.holdings)} holdings...")
        
        now = datetime.now()
        opex = get_next_opex(now)
        self.log(f"  📅 Next options expiry: {opex.strftime('%Y-%m-%d')}")
        self.log(f"  📅 Current month: {now.strftime('%B')} | Day: {now.strftime('%A')}")
        
        for holding in self.state.holdings:
            ticker = holding.ticker
            current_price = holding.current_price or holding.avg_buy_price
            
            entry_start, entry_end, urgency = self._compute_entry_urgency(ticker, holding.sector)
            
            # Get bull target for exit calculation
            bull = self.state.bull_theses.get(ticker)
            target = bull.price_target if bull else current_price * 1.15
            
            exit_start, exit_end = self._compute_exit_window(ticker, entry_start, current_price, target)
            
            # Entry price zone: use support level + slight buffer
            support = self.state.price_data.get(ticker, {}).get("support")
            resistance = self.state.price_data.get(ticker, {}).get("resistance")
            
            ta = self.state.technical_signals.get(ticker)
            
            # Ideal entry: at or near support, or current price if bullish momentum
            if support and current_price > support:
                entry_low  = round(max(support, current_price * 0.98), 2)
                entry_high = round(current_price * 1.01, 2)
            else:
                entry_low  = round(current_price * 0.99, 2)
                entry_high = round(current_price * 1.02, 2)
            
            # Store in recommendations (partial — will be completed by Strategist)
            if ticker not in self.state.recommendations:
                from core.state import TradeRecommendation
                self.state.recommendations[ticker] = TradeRecommendation(ticker=ticker, action="HOLD")
            
            rec = self.state.recommendations[ticker]
            rec.entry_window_start = entry_start
            rec.entry_window_end   = entry_end
            rec.entry_price_low    = entry_low
            rec.entry_price_high   = entry_high
            rec.exit_target_1      = target
            rec.exit_target_2      = round(target * 1.10, 2) if target else None
            rec.urgency            = urgency
            
            # Seasonality note
            season_score = self._get_seasonality_score(holding.sector, now.month)
            season_note = "✅ Seasonally strong month" if season_score == 1.0 else (
                "⚡ Approaching strong season" if season_score == 0.5 else "❄️ Off-season"
            )
            
            self.log(
                f"  ⏰ {ticker}: Entry {entry_start}→{entry_end} @ ${entry_low:.2f}-${entry_high:.2f} | "
                f"Urgency={urgency} | Exit Target ${target:.2f} | {season_note}"
            )
        
        self.log("✅ Time-precision windows computed.")
