"""
Agent 11: Risk Manager Agent
Calculates VaR, Sharpe ratio, max drawdown, beta, position sizing, stop-losses.
The risk manager has veto power over final recommendations.
"""
import asyncio
import pandas as pd
import numpy as np
from agents.base_agent import BaseAgent
from core.state import RiskMetrics


class RiskManagerAgent(BaseAgent):
    name = "RiskManager"
    description = "Bridgewater Associates risk analyst. Evaluates correlation, VaR, Sharpe, and tail risks."

    def _compute_beta(self, ticker_returns: pd.Series, spy_df: pd.DataFrame) -> float:
        """Compute beta vs S&P 500."""
        try:
            spy_returns = spy_df["Close"].pct_change().dropna()
            # Align by date
            aligned = pd.DataFrame({"stock": ticker_returns, "spy": spy_returns}).dropna()
            if len(aligned) < 30:
                return 1.0
            cov = aligned["stock"].cov(aligned["spy"])
            var = aligned["spy"].var()
            beta = cov / var if var > 0 else 1.0
            return round(beta, 3)
        except Exception:
            return 1.0

    def _grade_risk(self, var95: float, sharpe: float, beta: float, drawdown: float) -> str:
        """Grade overall risk level."""
        score = 0
        
        # VaR (lower is better)
        if var95 < 2:    score += 30
        elif var95 < 4:  score += 20
        elif var95 < 6:  score += 10
        else:            score += 0
        
        # Sharpe (higher is better)
        if sharpe > 1.5: score += 30
        elif sharpe > 1: score += 20
        elif sharpe > 0: score += 10
        else:            score += 0
        
        # Beta (closer to 1 is neutral, < 1 is defensive)
        if 0.5 < beta < 1.2: score += 20
        elif beta < 1.5:     score += 10
        else:                score += 0
        
        # Max Drawdown (less negative is better)
        if drawdown > -15:   score += 20
        elif drawdown > -25: score += 10
        else:                score += 0
        
        if score >= 80: return "A"
        if score >= 60: return "B"
        if score >= 40: return "C"
        if score >= 20: return "D"
        return "F"

    def _recommended_position_size(
        self, var95: float, sharpe: float, settings: dict
    ) -> float:
        """Kelly-inspired position sizing with VaR constraint."""
        max_pos = settings.get("max_position_size_pct", 25)
        
        # Base size on Sharpe (higher Sharpe = larger position allowed)
        if sharpe > 1.5:    base = max_pos
        elif sharpe > 1.0:  base = max_pos * 0.8
        elif sharpe > 0.5:  base = max_pos * 0.6
        elif sharpe > 0:    base = max_pos * 0.4
        else:               base = max_pos * 0.2
        
        # Risk constraint: don't let VaR exceed 3% of position value per day
        var_limit = 3.0 / var95 * 10 if var95 > 0 else max_pos
        
        return round(min(base, var_limit, max_pos), 1)

    async def run(self):
        self.log(f"⚠️ [BRIDGEWATER ASSOCIATES MODE] Running radical transparency risk analysis on {len(self.state.holdings)} holdings...")
        
        # Fetch SPY for beta calculation
        spy_df = self.use_tool("fetch_ohlcv", ticker="SPY", period="6mo", interval="1d")
        
        total_portfolio_var = 0.0
        portfolio_sharpes = []
        
        for holding in self.state.holdings:
            ticker = holding.ticker
            data = self.state.price_data.get(ticker, {})
            df = data.get("df_6mo") if data else None
            
            if df is None or (hasattr(df, 'empty') and df.empty):
                self.log(f"  No price data for {ticker}, using avg-cost estimates")
                current = holding.current_price or holding.avg_buy_price
                stop_loss_pct = self.state.settings.get("stop_loss_pct", 8) / 100
                take_profit_pct = self.state.settings.get("take_profit_pct", 20) / 100
                self.state.risk_metrics[ticker] = RiskMetrics(
                    ticker=ticker,
                    var_95=3.5, var_99=5.0,
                    max_drawdown=-15.0, sharpe_ratio=0.5,
                    beta=1.2, volatility_annual=25.0,
                    recommended_position_pct=10.0,
                    stop_loss_price=round(current * (1 - stop_loss_pct), 2),
                    take_profit_price=round(current * (1 + take_profit_pct), 2),
                    risk_grade="C",
                )
                portfolio_sharpes.append(0.5)
                continue
            
            returns = self.use_tool("calculate_returns", df=df)
            
            var95  = self.use_tool("compute_var", returns=returns, confidence=0.95)
            var99  = self.use_tool("compute_var", returns=returns, confidence=0.99)
            sharpe = self.use_tool("compute_sharpe", returns=returns)
            mdd    = self.use_tool("compute_max_drawdown", prices=df["Close"])
            
            beta = self._compute_beta(returns, spy_df) if spy_df is not None else 1.0
            
            # Annualized volatility
            vol_annual = float(returns.std() * np.sqrt(252) * 100)
            
            # Stop-loss: current price - (ATR * multiplier) OR fixed pct
            current = holding.current_price or holding.avg_buy_price
            stop_loss_pct = self.state.settings.get("stop_loss_pct", 8) / 100
            take_profit_pct = self.state.settings.get("take_profit_pct", 20) / 100
            
            # ATR-based stop (tighter when ATR is low)
            ta = self.state.technical_signals.get(ticker)
            if ta and ta.atr_14 and current > 0:
                atr_stop = current - (ta.atr_14 * 2.5)
                pct_stop = current * (1 - stop_loss_pct)
                stop_loss_price = round(max(atr_stop, pct_stop), 2)
            else:
                stop_loss_price = round(current * (1 - stop_loss_pct), 2)
            
            take_profit_price = round(current * (1 + take_profit_pct), 2)
            
            risk_grade = self._grade_risk(var95, sharpe, beta, mdd)
            pos_size = self._recommended_position_size(var95, sharpe, self.state.settings)
            
            self.state.risk_metrics[ticker] = RiskMetrics(
                ticker=ticker,
                var_95=var95,
                var_99=var99,
                max_drawdown=mdd,
                sharpe_ratio=sharpe,
                beta=beta,
                volatility_annual=round(vol_annual, 2),
                recommended_position_pct=pos_size,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                risk_grade=risk_grade,
            )
            
            total_portfolio_var += (var95 * pos_size / 100) ** 2
            portfolio_sharpes.append(sharpe)
            
            sharpe_s = f"{sharpe:.2f}" if sharpe is not None else "N/A"
            var95_s  = f"{var95:.2f}" if var95 is not None else "N/A"
            self.log(
                f"  {ticker}: VaR95={var95_s}% | Sharpe={sharpe_s} | "
                f"Beta={beta:.2f} | MDD={mdd:.1f}% | "
                f"Stop=${stop_loss_price:.2f} | Grade={risk_grade} | Pos={pos_size:.0f}%"
            )
        
        # Portfolio-level metrics (simplified diversification effect)
        n = len(self.state.holdings)
        if n > 0:
            self.state.portfolio_var = round(np.sqrt(total_portfolio_var) * np.sqrt(n), 2)
            self.state.portfolio_sharpe = round(sum(portfolio_sharpes) / n, 3) if portfolio_sharpes else None
        
        self.log(
            f"✅ Portfolio VaR (95%): ~{self.state.portfolio_var:.2f}% | "
            f"Avg Sharpe: {self.state.portfolio_sharpe:.2f}"
        )
