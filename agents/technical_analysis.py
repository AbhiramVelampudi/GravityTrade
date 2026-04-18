"""
Agent 4: Technical Analysis Agent
Computes RSI, MACD, Bollinger Bands, EMA, ATR, OBV, VWAP, and composite TA score.
"""
import asyncio
import pandas as pd
import numpy as np
import pandas_ta as ta
from agents.base_agent import BaseAgent
from core.state import TechnicalSignals


class TechnicalAnalysisAgent(BaseAgent):
    name = "TechnicalAnalysis"
    description = "Citadel quantitative trader combining TA with statistical models to time entries and exits."

    def _score_rsi(self, rsi: float) -> float:
        """Score RSI: oversold=bullish(high score), overbought=bearish(low score)."""
        if rsi is None: return 50.0
        if rsi < 30:   return 85.0
        if rsi < 40:   return 70.0
        if rsi < 50:   return 55.0
        if rsi < 60:   return 50.0
        if rsi < 70:   return 40.0
        return 20.0  # overbought

    def _score_macd(self, macd: float, signal: float, histogram: float) -> float:
        """Score MACD crossover state."""
        if any(v is None for v in [macd, signal, histogram]): return 50.0
        if histogram > 0 and macd > signal: return 70.0
        if histogram > 0 and macd < signal: return 55.0
        if histogram < 0 and macd > signal: return 45.0
        return 30.0

    def _score_bb(self, close: float, upper: float, lower: float, middle: float) -> float:
        """Score Bollinger Band position."""
        if any(v is None for v in [close, upper, lower, middle]): return 50.0
        band_width = upper - lower
        if band_width == 0: return 50.0
        position = (close - lower) / band_width
        if position < 0.1:  return 85.0   # near lower band = oversold bounce
        if position < 0.3:  return 65.0
        if position < 0.7:  return 50.0
        if position < 0.9:  return 35.0
        return 20.0  # near upper = overbought

    def _score_ema(self, close: float, ema50: float, ema200: float) -> float:
        """Score EMA relationship (golden/death cross proxy)."""
        if any(v is None for v in [close, ema50, ema200]): return 50.0
        if close > ema50 > ema200: return 80.0   # strong uptrend
        if close > ema50:          return 65.0
        if close < ema50 < ema200: return 25.0   # strong downtrend
        if close < ema50:          return 40.0
        return 50.0

    def _signal_from_score(self, score: float) -> str:
        if score >= 70: return "BUY"
        if score >= 55: return "WATCH"
        if score >= 45: return "HOLD"
        if score >= 30: return "CAUTION"
        return "SELL"

    async def run(self):
        self.log(f"📈 [CITADEL QUANTITATIVE TRADER MODE] Running technical analysis on {len(self.state.holdings)} holdings...")
        
        for holding in self.state.holdings:
            ticker = holding.ticker
            data = self.state.price_data.get(ticker, {})
            df = data.get("df_6mo")
            
            if df is None or df.empty or len(df) < 30:
                self.log(f"  ⚠️ Insufficient data for {ticker}", level="warning")
                self.state.technical_signals[ticker] = TechnicalSignals(ticker=ticker, ta_signal="HOLD")
                continue
            
            self.log(f"  ↳ Calculating indicators for {ticker} ({len(df)} bars)...")
            
            close = df["Close"]
            high  = df["High"]
            low   = df["Low"]
            vol   = df["Volume"]
            
            # RSI
            rsi_series = ta.rsi(close, length=14)
            try:
                rsi_raw = float(rsi_series.iloc[-1]) if rsi_series is not None and not rsi_series.empty else None
                rsi = None if rsi_raw is None or pd.isna(rsi_raw) else rsi_raw
            except Exception:
                rsi = None
            
            # MACD
            macd_df = ta.macd(close, fast=12, slow=26, signal=9)
            if macd_df is not None and not macd_df.empty:
                macd_val   = float(macd_df.iloc[-1, 0]) if not pd.isna(macd_df.iloc[-1, 0]) else None
                macd_hist  = float(macd_df.iloc[-1, 1]) if not pd.isna(macd_df.iloc[-1, 1]) else None
                macd_sig   = float(macd_df.iloc[-1, 2]) if not pd.isna(macd_df.iloc[-1, 2]) else None
            else:
                macd_val = macd_hist = macd_sig = None
            
            # Bollinger Bands
            bb_df = ta.bbands(close, length=20, std=2)
            if bb_df is not None and not bb_df.empty:
                bb_lower  = float(bb_df.iloc[-1, 0]) if not pd.isna(bb_df.iloc[-1, 0]) else None
                bb_middle = float(bb_df.iloc[-1, 1]) if not pd.isna(bb_df.iloc[-1, 1]) else None
                bb_upper  = float(bb_df.iloc[-1, 2]) if not pd.isna(bb_df.iloc[-1, 2]) else None
            else:
                bb_lower = bb_middle = bb_upper = None
            
            # EMAs
            def safe_ema(s, n):
                try:
                    v = ta.ema(s, length=n)
                    val = float(v.iloc[-1]) if v is not None and not v.empty else None
                    return None if val is None or pd.isna(val) else val
                except Exception:
                    return None
            ema9   = safe_ema(close, 9)
            ema21  = safe_ema(close, 21)
            ema50  = safe_ema(close, 50)
            ema200 = safe_ema(close, 200)
            
            # ATR
            atr_series = ta.atr(high, low, close, length=14)
            atr = float(atr_series.iloc[-1]) if atr_series is not None and not atr_series.empty else None
            
            # OBV
            obv_series = ta.obv(close, vol)
            obv = float(obv_series.iloc[-1]) if obv_series is not None and not obv_series.empty else None
            
            # VWAP (approximate with pandas-ta)
            try:
                vwap_series = ta.vwap(high, low, close, vol)
                vwap = float(vwap_series.iloc[-1]) if vwap_series is not None and not vwap_series.empty else None
            except Exception:
                vwap = float((close * vol).sum() / vol.sum()) if vol.sum() > 0 else None
            
            # Volume ratio (current vs 20-day average)
            avg_vol_20 = vol.rolling(20).mean().iloc[-1]
            current_vol = vol.iloc[-1]
            volume_ratio = float(current_vol / avg_vol_20) if avg_vol_20 > 0 else 1.0
            
            current_close = float(close.iloc[-1])
            
            # Composite TA Score (weighted average)
            score_rsi  = self._score_rsi(rsi)
            score_macd = self._score_macd(macd_val, macd_sig, macd_hist)
            score_bb   = self._score_bb(current_close, bb_upper, bb_lower, bb_middle)
            score_ema  = self._score_ema(current_close, ema50, ema200)
            
            # Volume confirmation bonus/penalty
            vol_bonus = 5.0 if volume_ratio > 1.5 else (-5.0 if volume_ratio < 0.5 else 0.0)
            
            ta_score = (
                score_rsi  * 0.30 +
                score_macd * 0.30 +
                score_bb   * 0.20 +
                score_ema  * 0.20 +
                vol_bonus
            )
            ta_score = max(0.0, min(100.0, ta_score))
            
            signals = TechnicalSignals(
                ticker=ticker,
                rsi_14=round(rsi, 2) if rsi else None,
                macd=round(macd_val, 4) if macd_val else None,
                macd_signal=round(macd_sig, 4) if macd_sig else None,
                macd_histogram=round(macd_hist, 4) if macd_hist else None,
                bb_upper=round(bb_upper, 4) if bb_upper else None,
                bb_middle=round(bb_middle, 4) if bb_middle else None,
                bb_lower=round(bb_lower, 4) if bb_lower else None,
                ema_9=round(ema9, 4) if ema9 else None,
                ema_21=round(ema21, 4) if ema21 else None,
                ema_50=round(ema50, 4) if ema50 else None,
                ema_200=round(ema200, 4) if ema200 else None,
                atr_14=round(atr, 4) if atr else None,
                obv=round(obv, 0) if obv else None,
                vwap=round(vwap, 4) if vwap else None,
                volume_ratio=round(volume_ratio, 2),
                ta_score=round(ta_score, 1),
                ta_signal=self._signal_from_score(ta_score),
            )
            
            self.state.technical_signals[ticker] = signals
            rsi_str = f"{rsi:.1f}" if rsi is not None else "N/A"
            macd_dir = "up" if macd_hist and macd_hist > 0 else "dn"
            self.log(
                f"  {ticker}: RSI={rsi_str} | MACD={macd_dir} | "
                f"TA Score={ta_score:.0f}/100 | Signal={signals.ta_signal}"
            )
        
        self.log("✅ Technical analysis complete for all holdings.")
