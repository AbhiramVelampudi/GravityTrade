"""
Agent 3: Market Data Agent
Fetches full OHLCV history and stores in shared state for downstream agents.
"""
import asyncio
import pandas as pd
from agents.base_agent import BaseAgent


class MarketDataAgent(BaseAgent):
    name = "MarketData"
    description = "Fetches OHLCV history, volume data, and 52-week context for all holdings."

    async def run(self):
        self.log(f"📊 Fetching market data for {len(self.state.holdings)} holdings...")
        
        tickers = [h.ticker for h in self.state.holdings]
        
        for ticker in tickers:
            self.log(f"  ↳ Fetching 6-month OHLCV for {ticker}...")
            
            # Fetch 6mo daily for TA calculations
            df_6mo = self.use_tool("fetch_ohlcv", ticker=ticker, period="6mo", interval="1d")
            # Fetch 2y for pattern recognition and drawdown
            df_2y = self.use_tool("fetch_ohlcv", ticker=ticker, period="2y", interval="1d")
            # Fetch 1w hourly for short-term precision
            df_1w = self.use_tool("fetch_ohlcv", ticker=ticker, period="5d", interval="60m")
            
            self.state.price_data[ticker] = {
                "df_6mo": df_6mo,
                "df_2y": df_2y,
                "df_1w": df_1w,
            }
            
            if df_6mo is not None:
                latest = df_6mo.iloc[-1]
                prev = df_6mo.iloc[-2] if len(df_6mo) > 1 else latest
                day_change = ((latest["Close"] - prev["Close"]) / prev["Close"]) * 100
                self.log(
                    f"  ✅ {ticker}: Close ${latest['Close']:.2f} | "
                    f"Day Change: {'+'if day_change>=0 else ''}{day_change:.2f}% | "
                    f"Vol: {int(latest['Volume']):,}"
                )
            else:
                self.log(f"  ⚠️ No data for {ticker}", level="warning")
        
        self.log("✅ Market data fetched for all tickers.")
