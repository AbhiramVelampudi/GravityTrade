"""
Agent 2: Portfolio Ingestor
Reads the user's portfolio.json and populates state.holdings with live prices.
"""
import json
import asyncio
from pathlib import Path

from agents.base_agent import BaseAgent
from core.state import Holding, PortfolioState


class PortfolioIngestorAgent(BaseAgent):
    name = "PortfolioIngestor"
    description = "Reads and validates the user's portfolio, enriches with live prices."

    async def run(self):
        self.log("📦 Loading portfolio from data/portfolio.json...")
        
        portfolio_path = Path("data/portfolio.json")
        if not portfolio_path.exists():
            self.log("❌ portfolio.json not found!", level="error")
            return

        with open(portfolio_path) as f:
            raw = json.load(f)
        
        self.state.settings = raw.get("settings", {})
        holdings_raw = raw.get("portfolio", [])
        
        total_value = 0.0
        total_cost = 0.0
        
        for h in holdings_raw:
            ticker = h["ticker"]
            try:
                self.log(f"  ↳ Fetching live price for {ticker}...")
                quote = self.use_tool("get_live_price", ticker=ticker)
                
                if quote and quote.get("price"):
                    current_price = float(quote["price"])
                else:
                    raise ValueError("No price")
            except Exception:
                self.log(f"  ⚠️ No live price for {ticker}, using avg_buy_price", level="warning")
                current_price = h["avg_buy_price"]
            
            shares = h["shares"]
            avg_buy = h["avg_buy_price"]
            market_val = shares * current_price
            cost_basis = shares * avg_buy
            pnl = market_val - cost_basis
            pnl_pct = (pnl / cost_basis) * 100
            
            holding = Holding(
                ticker=ticker,
                name=h["name"],
                shares=shares,
                avg_buy_price=avg_buy,
                sector=h["sector"],
                currency=h.get("currency", "USD"),
                current_price=round(current_price, 4),
                market_value=round(market_val, 2),
                unrealized_pnl=round(pnl, 2),
                unrealized_pnl_pct=round(pnl_pct, 2),
            )
            self.state.holdings.append(holding)
            
            total_value += market_val
            total_cost += cost_basis
            
            self.log(
                f"  ✅ {ticker}: ${current_price:.2f} | "
                f"Value: ${market_val:,.2f} | "
                f"P&L: {'+'if pnl>=0 else ''}{pnl_pct:.1f}%"
            )
        
        self.state.total_portfolio_value = round(total_value, 2)
        self.state.total_cost_basis = round(total_cost, 2)
        self.state.total_pnl = round(total_value - total_cost, 2)
        self.state.total_pnl_pct = round(((total_value - total_cost) / total_cost) * 100, 2)
        
        self.log(
            f"✅ Portfolio loaded: {len(self.state.holdings)} holdings | "
            f"Total Value: ${total_value:,.2f} | "
            f"Total P&L: {'+'if self.state.total_pnl>=0 else ''}{self.state.total_pnl_pct:.1f}%"
        )
