"""
core/mcp_tools.py — MCP Tool Registry v2
All tools now use the multi-API data engine cascade.
"""
import logging
import numpy as np
from typing import Optional, Dict, Any, List

from core.data_engine import get_realtime_quote, get_ohlcv, get_news, get_fundamentals, get_macro

logger = logging.getLogger("core.mcp_tools")


class MCPToolRegistry:
    """Central tool registry — all agents call tools through here."""

    def __init__(self):
        self._tools = {}
        self._register_all()

    def call(self, tool_name: str, **kwargs) -> Any:
        if tool_name not in self._tools:
            raise ValueError(f"Unknown tool: {tool_name}")
        return self._tools[tool_name](**kwargs)

    def _register_all(self):
        self._tools = {
            "get_live_price":       self._get_live_price,
            "fetch_ohlcv":          self._fetch_ohlcv,
            "get_fundamentals":     self._get_fundamentals,
            "fetch_macro_data":     self._fetch_macro_data,
            "fetch_news_headlines": self._fetch_news_headlines,
            "calculate_returns":    self._calculate_returns,
            "compute_var":          self._compute_var,
            "compute_sharpe":       self._compute_sharpe,
            "compute_max_drawdown": self._compute_max_drawdown,
            "compute_beta":         self._compute_beta,
            "compute_support_resistance": self._compute_support_resistance,
        }

    # ── LIVE PRICE ──────────────────────────────────────────
    def _get_live_price(self, ticker: str) -> Dict:
        result = get_realtime_quote(ticker)
        logger.info(f"Live price {ticker}: ${result.get('price')} [{result.get('source')}]")
        return result

    # ── OHLCV ───────────────────────────────────────────────
    def _fetch_ohlcv(self, ticker: str, period: str = "6mo", interval: str = "1d") -> Optional[Any]:
        period_map = {"5d": 5, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730}
        days = period_map.get(period, 180)
        df = get_ohlcv(ticker, period_days=days)
        if df is None or (hasattr(df, 'empty') and df.empty):
            logger.warning(f"No OHLCV data for {ticker}")
            return None

        # Add support/resistance
        sr = self._compute_support_resistance(df=df)
        df.attrs["support"] = sr.get("support")
        df.attrs["resistance"] = sr.get("resistance")
        return df

    # ── FUNDAMENTALS ─────────────────────────────────────────
    def _get_fundamentals(self, ticker: str) -> Dict:
        data = get_fundamentals(ticker)
        src = data.get("source_fundamentals", "unknown")
        logger.info(f"Fundamentals {ticker}: P/E={data.get('pe_ratio')} [{src}]")
        return data

    # ── MACRO ────────────────────────────────────────────────
    def _fetch_macro_data(self) -> Dict:
        data = get_macro()
        logger.info(f"Macro: VIX={data.get('vix')} SPX={data.get('sp500_current')} Spread={data.get('yield_curve_spread')}")
        return data

    # ── NEWS ─────────────────────────────────────────────────
    def _fetch_news_headlines(self, ticker: str, max_articles: int = 20) -> List[Dict]:
        articles = get_news(ticker, max_items=max_articles)
        logger.info(f"News {ticker}: {len(articles)} articles")
        return articles

    # ── RETURNS ──────────────────────────────────────────────
    def _calculate_returns(self, df) -> Optional[Any]:
        try:
            close = df["Close"] if "Close" in df.columns else df.iloc[:, 3]
            returns = close.pct_change().dropna()
            return returns
        except Exception as e:
            logger.error(f"calculate_returns: {e}")
            return None

    # ── VAR ──────────────────────────────────────────────────
    def _compute_var(self, returns, confidence: float = 0.95) -> Optional[float]:
        try:
            if returns is None or len(returns) < 20:
                return None
            arr = returns.dropna().values
            var = float(-np.percentile(arr, (1 - confidence) * 100) * 100)
            return round(var, 3)
        except Exception as e:
            logger.error(f"compute_var: {e}")
            return None

    # ── SHARPE ───────────────────────────────────────────────
    def _compute_sharpe(self, returns, risk_free_rate: float = 0.05) -> Optional[float]:
        try:
            if returns is None or len(returns) < 20:
                return None
            arr = returns.dropna().values
            daily_rf = risk_free_rate / 252
            excess = arr - daily_rf
            sharpe = float(np.mean(excess) / np.std(excess, ddof=1) * np.sqrt(252))
            return round(sharpe, 3)
        except Exception as e:
            logger.error(f"compute_sharpe: {e}")
            return None

    # ── MAX DRAWDOWN ─────────────────────────────────────────
    def _compute_max_drawdown(self, prices) -> Optional[float]:
        try:
            if prices is None or len(prices) < 5:
                return None
            arr = prices.values if hasattr(prices, 'values') else np.array(prices)
            peak = np.maximum.accumulate(arr)
            drawdowns = (arr - peak) / peak * 100
            return round(float(np.min(drawdowns)), 2)
        except Exception as e:
            logger.error(f"compute_max_drawdown: {e}")
            return None

    # ── BETA ─────────────────────────────────────────────────
    def _compute_beta(self, stock_returns, market_returns=None) -> float:
        try:
            if market_returns is None or len(market_returns) < 10:
                return 1.2  # Market beta default
            common = stock_returns.align(market_returns, join='inner')
            s = common[0].dropna().values
            m = common[1].dropna().values
            if len(s) < 10:
                return 1.2
            cov = np.cov(s, m)
            return round(float(cov[0, 1] / cov[1, 1]), 3) if cov[1, 1] != 0 else 1.2
        except Exception:
            return 1.2

    # ── SUPPORT/RESISTANCE ───────────────────────────────────
    def _compute_support_resistance(self, df) -> Dict:
        try:
            close = df["Close"].values
            n = len(close)
            if n < 20:
                return {"support": float(close[-1] * 0.95), "resistance": float(close[-1] * 1.05)}
            recent = close[-60:] if n >= 60 else close
            support    = float(np.percentile(recent, 15))
            resistance = float(np.percentile(recent, 85))
            return {"support": round(support, 2), "resistance": round(resistance, 2)}
        except Exception:
            return {"support": None, "resistance": None}


# Singleton
_registry = None
def get_registry() -> MCPToolRegistry:
    global _registry
    if _registry is None:
        _registry = MCPToolRegistry()
    return _registry
