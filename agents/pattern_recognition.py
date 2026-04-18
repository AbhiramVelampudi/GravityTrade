"""
Agent 10: Pattern Recognition Agent
Detects key chart patterns: double tops/bottoms, breakouts, support/resistance.
"""
import asyncio
import pandas as pd
import numpy as np
from agents.base_agent import BaseAgent
from core.state import PatternAlert


class PatternRecognitionAgent(BaseAgent):
    name = "PatternRecognition"
    description = "Renaissance Technologies quant researcher finding hidden statistical edges, seasonality, and chart anomalies."

    def _detect_support_resistance(self, df: pd.DataFrame, window: int = 20) -> dict:
        """Find key support and resistance levels using rolling min/max."""
        if len(df) < window * 2:
            return {"support": None, "resistance": None}
        
        recent = df.tail(window * 2)
        resistance = float(recent["High"].max())
        support = float(recent["Low"].min())
        
        # Find local pivots (more refined)
        highs = df["High"].rolling(window=5, center=True).max()
        lows  = df["Low"].rolling(window=5, center=True).min()
        
        # Strong support = recent low that held multiple times
        strong_support = float(lows.tail(60).nsmallest(3).mean())
        strong_resistance = float(highs.tail(60).nlargest(3).mean())
        
        return {
            "support": round(strong_support, 2),
            "resistance": round(strong_resistance, 2),
            "range_support": round(support, 2),
            "range_resistance": round(resistance, 2),
        }

    def _detect_breakout(self, df: pd.DataFrame) -> dict:
        """Detect if price is breaking out of a consolidation range."""
        if len(df) < 30:
            return {"type": None}
        
        recent_20 = df.tail(20)
        prior_20  = df.iloc[-40:-20] if len(df) >= 40 else df.head(20)
        
        current_close = float(df["Close"].iloc[-1])
        prior_high    = float(prior_20["High"].max())
        prior_low     = float(prior_20["Low"].min())
        recent_avg_vol = float(recent_20["Volume"].mean())
        prior_avg_vol  = float(prior_20["Volume"].mean())
        vol_expansion  = recent_avg_vol / prior_avg_vol if prior_avg_vol > 0 else 1.0
        
        if current_close > prior_high * 1.02 and vol_expansion > 1.2:
            return {"type": "BULLISH_BREAKOUT", "level": round(prior_high, 2), "vol_expansion": round(vol_expansion, 2)}
        if current_close < prior_low * 0.98 and vol_expansion > 1.2:
            return {"type": "BEARISH_BREAKDOWN", "level": round(prior_low, 2), "vol_expansion": round(vol_expansion, 2)}
        
        return {"type": None}

    def _detect_double_bottom(self, df: pd.DataFrame) -> bool:
        """Simple double bottom detection."""
        if len(df) < 60:
            return False
        lows = df["Low"].tail(60)
        min1_idx = lows.idxmin()
        lows_after = lows[lows.index > min1_idx]
        if lows_after.empty:
            return False
        min2 = float(lows_after.min())
        min1 = float(lows.min())
        # Double bottom: two lows within 3% of each other
        return abs(min2 - min1) / min1 < 0.03

    def _detect_double_top(self, df: pd.DataFrame) -> bool:
        """Simple double top detection."""
        if len(df) < 60:
            return False
        highs = df["High"].tail(60)
        max1_idx = highs.idxmax()
        highs_after = highs[highs.index > max1_idx]
        if highs_after.empty:
            return False
        max2 = float(highs_after.max())
        max1 = float(highs.max())
        return abs(max2 - max1) / max1 < 0.03

    def _detect_trend_channel(self, df: pd.DataFrame) -> dict:
        """Detect uptrend or downtrend channel using linear regression."""
        if len(df) < 30:
            return {"type": "UNDEFINED"}
        
        closes = df["Close"].tail(30).reset_index(drop=True)
        x = np.arange(len(closes))
        coeffs = np.polyfit(x, closes, 1)
        slope = coeffs[0]
        
        slope_pct = slope / float(closes.mean()) * 100
        
        if slope_pct > 0.3:    return {"type": "UPTREND", "slope_pct_daily": round(slope_pct, 3)}
        if slope_pct < -0.3:   return {"type": "DOWNTREND", "slope_pct_daily": round(slope_pct, 3)}
        return {"type": "SIDEWAYS", "slope_pct_daily": round(slope_pct, 3)}

    def _detect_volume_climax(self, df: pd.DataFrame) -> dict:
        """Detect unusual volume spikes that may signal reversals."""
        if len(df) < 20:
            return {"type": None}
        avg_vol = float(df["Volume"].tail(20).mean())
        current_vol = float(df["Volume"].iloc[-1])
        ratio = current_vol / avg_vol if avg_vol > 0 else 1.0
        current_change = float((df["Close"].iloc[-1] - df["Close"].iloc[-2]) / df["Close"].iloc[-2])
        
        if ratio > 2.5 and current_change > 0.02:
            return {"type": "VOLUME_SURGE_BULLISH", "ratio": round(ratio, 2)}
        if ratio > 2.5 and current_change < -0.02:
            return {"type": "VOLUME_SURGE_BEARISH", "ratio": round(ratio, 2)}
        return {"type": None}

    async def run(self):
        self.log(f"🔎 [RENAISSANCE TECH MODE] Running statistical pattern recognition on {len(self.state.holdings)} holdings...")
        
        for holding in self.state.holdings:
            ticker = holding.ticker
            data = self.state.price_data.get(ticker, {})
            df_2y = data.get("df_2y")
            df_6mo = data.get("df_6mo")
            
            df = df_2y if df_2y is not None and not df_2y.empty else df_6mo
            
            if df is None or df.empty:
                self.log(f"  ⚠️ No data for {ticker}", level="warning")
                continue
            
            alerts = []
            
            # Support/Resistance
            sr = self._detect_support_resistance(df)
            
            # Breakout detection
            breakout = self._detect_breakout(df)
            if breakout["type"] == "BULLISH_BREAKOUT":
                alerts.append(PatternAlert(
                    ticker=ticker,
                    pattern_name="Bullish Breakout",
                    pattern_type="bullish",
                    reliability=0.72,
                    description=f"Price broke above ${breakout['level']:.2f} resistance with {breakout['vol_expansion']:.1f}x volume surge",
                    price_target=holding.current_price * 1.10 if holding.current_price else None,
                    detected_at=holding.current_price,
                ))
            elif breakout["type"] == "BEARISH_BREAKDOWN":
                alerts.append(PatternAlert(
                    ticker=ticker,
                    pattern_name="Bearish Breakdown",
                    pattern_type="bearish",
                    reliability=0.70,
                    description=f"Price broke below ${breakout['level']:.2f} support with high volume",
                    detected_at=holding.current_price,
                ))
            
            # Double bottom (bullish reversal)
            if self._detect_double_bottom(df):
                alerts.append(PatternAlert(
                    ticker=ticker,
                    pattern_name="Double Bottom",
                    pattern_type="bullish",
                    reliability=0.68,
                    description="Double bottom reversal pattern detected — potential strong bounce",
                    price_target=sr.get("resistance"),
                    detected_at=holding.current_price,
                ))
            
            # Double top (bearish reversal)
            if self._detect_double_top(df):
                alerts.append(PatternAlert(
                    ticker=ticker,
                    pattern_name="Double Top",
                    pattern_type="bearish",
                    reliability=0.65,
                    description="Double top pattern detected — distribution phase, watch for breakdown",
                    price_target=sr.get("support"),
                    detected_at=holding.current_price,
                ))
            
            # Trend channel
            trend = self._detect_trend_channel(df)
            if trend["type"] != "UNDEFINED":
                pat_type = "bullish" if trend["type"] == "UPTREND" else ("bearish" if trend["type"] == "DOWNTREND" else "neutral")
                alerts.append(PatternAlert(
                    ticker=ticker,
                    pattern_name=f"Trend Channel ({trend['type']})",
                    pattern_type=pat_type,
                    reliability=0.60,
                    description=f"{trend['type']} trend channel — slope {trend.get('slope_pct_daily', 0):+.3f}%/day over 30 sessions",
                    detected_at=holding.current_price,
                ))
            
            # Volume climax
            vol_climax = self._detect_volume_climax(df)
            if vol_climax["type"]:
                pat_type = "bullish" if "BULLISH" in vol_climax["type"] else "bearish"
                alerts.append(PatternAlert(
                    ticker=ticker,
                    pattern_name="Volume Climax",
                    pattern_type=pat_type,
                    reliability=0.65,
                    description=f"Unusual {vol_climax['ratio']:.1f}x volume spike — potential institutional activity",
                    detected_at=holding.current_price,
                ))
            
            # Always add support/resistance info
            if sr.get("support") and sr.get("resistance"):
                self.state.price_data[ticker]["support"] = sr["support"]
                self.state.price_data[ticker]["resistance"] = sr["resistance"]
            
            self.state.pattern_alerts[ticker] = alerts
            
            pattern_names = [a.pattern_name for a in alerts] if alerts else ["No significant patterns"]
            self.log(f"  ✅ {ticker}: {len(alerts)} patterns — {', '.join(pattern_names)}")
        
        self.log("✅ Pattern recognition complete.")
