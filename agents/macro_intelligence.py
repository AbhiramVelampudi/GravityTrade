"""
Agent 7: Macro Intelligence Agent
Analyzes Fed rates, yield curve, VIX, S&P500 trend, dollar index.
Determines the macro tailwind/headwind for equities.
"""
import asyncio
from agents.base_agent import BaseAgent
from core.state import MacroData


class MacroIntelligenceAgent(BaseAgent):
    name = "MacroIntelligence"
    description = "McKinsey Global Institute macro analyst. Advises on economic trends, Fed rates, yield curve, and SPX trend."

    def _score_vix(self, vix: float) -> float:
        """Low VIX = calm market = bullish. High VIX = fear = bearish."""
        if vix is None: return 50.0
        if vix < 15:   return 80.0   # very calm
        if vix < 20:   return 65.0   # normal
        if vix < 25:   return 50.0   # elevated
        if vix < 30:   return 35.0   # high fear
        return 15.0  # extreme fear

    def _score_yield_curve(self, spread: float) -> float:
        """Positive spread (10Y > 2Y) = healthy. Inverted = recession warning."""
        if spread is None: return 50.0
        if spread > 1.0:   return 80.0   # healthy
        if spread > 0.5:   return 65.0
        if spread > 0.0:   return 55.0
        if spread > -0.5:  return 40.0   # slightly inverted
        return 20.0  # deeply inverted — recession signal

    def _score_sp500(self, trend: str, change_1m: float) -> float:
        if trend == "UP":
            return 70.0 + min(10.0, (change_1m or 0) * 0.5)
        if trend == "DOWN":
            return 35.0 + max(-10.0, (change_1m or 0) * 0.5)
        return 50.0

    def _macro_signal(self, score: float) -> str:
        if score >= 70: return "RISK_ON"         # Strong buy environment
        if score >= 55: return "CAUTIOUSLY_BULLISH"
        if score >= 45: return "NEUTRAL"
        if score >= 30: return "CAUTIOUSLY_BEARISH"
        return "RISK_OFF"                         # De-risk / sell

    async def run(self):
        self.log("🌍 [MCKINSEY GLOBAL INSTITUTE MODE] Fetching macroeconomic indicators...")
        
        raw = self.use_tool("fetch_macro_data")
        
        vix        = raw.get("vix")
        ycurve     = raw.get("yield_curve_spread")
        sp_trend   = raw.get("sp500_trend", "UNKNOWN")
        sp_change  = raw.get("sp500_1m_change", 0)
        yield_10y  = raw.get("yield_10y")
        yield_2y   = raw.get("yield_2y")
        sp500_curr = raw.get("sp500_current")
        dollar_idx = raw.get("dollar_index")
        
        # Sub-scores
        s_vix   = self._score_vix(vix)
        s_yc    = self._score_yield_curve(ycurve)
        s_sp    = self._score_sp500(sp_trend, sp_change)
        
        # Dollar: strong dollar = headwind for multinationals
        s_dollar = 50.0  # neutral default
        if dollar_idx:
            if dollar_idx > 105:   s_dollar = 30.0   # very strong USD = headwind
            elif dollar_idx > 100: s_dollar = 45.0
            elif dollar_idx > 95:  s_dollar = 60.0
            else:                  s_dollar = 70.0   # weak USD = tailwind for intl revenue
        
        macro_score = (
            s_vix    * 0.35 +
            s_yc     * 0.30 +
            s_sp     * 0.25 +
            s_dollar * 0.10
        )
        macro_score = max(0.0, min(100.0, macro_score))
        
        self.state.macro_data = MacroData(
            vix=vix,
            yield_10y=yield_10y,
            yield_2y=yield_2y,
            yield_curve_spread=ycurve,
            sp500_trend=sp_trend,
            dollar_index=dollar_idx,
            macro_score=round(macro_score, 1),
            macro_signal=self._macro_signal(macro_score),
        )
        
        vix_s  = f"{vix:.1f}"  if vix   else "N/A"
        yc_s   = f"{ycurve:+.3f}" if ycurve else "N/A"
        t10_s  = str(yield_10y) if yield_10y else "N/A"
        dxy_s  = f"{dollar_idx:.1f}" if dollar_idx else "N/A"
        sp_s   = f"{sp_change:+.1f}%" if sp_change else "0.0%"
        self.log(f"  VIX: {vix_s} | Yield Curve: {yc_s}")
        self.log(f"  S&P 500: {sp_trend} ({sp_s} 1mo) | 10Y: {t10_s}%")
        self.log(f"  DXY: {dxy_s}")
        self.log(
            f"✅ Macro Score: {macro_score:.0f}/100 | "
            f"Signal: {self.state.macro_data.macro_signal}"
        )
