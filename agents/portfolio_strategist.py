"""
Agent 13: Portfolio Strategist — THE FINAL BOSS
Synthesizes ALL agent outputs into final BUY/SELL/HOLD/TRIM/ADD recommendations.
This is the decision engine. It weighs the bull vs bear debate, risk constraints,
technical signals, fundamentals, sentiment, and timing to produce peak decisions.
"""
import asyncio
from datetime import datetime
from agents.base_agent import BaseAgent
from core.state import TradeRecommendation


class PortfolioStrategistAgent(BaseAgent):
    name = "PortfolioStrategist"
    description = "BlackRock portfolio strategist (The Final Boss). Synthesizes all 12 agents into peak allocations."

    def _compute_composite_score(self, ticker: str) -> float:
        """
        Compute weighted composite score from all agents.
        Score 0-100: >65 = BUY, 50-65 = HOLD/WATCH, <50 = SELL/CAUTION
        """
        ta   = self.state.technical_signals.get(ticker)
        fund = self.state.fundamental_signals.get(ticker)
        sent = self.state.sentiment_signals.get(ticker)
        macro = self.state.macro_data
        bull = self.state.bull_theses.get(ticker)
        bear = self.state.bear_theses.get(ticker)
        risk = self.state.risk_metrics.get(ticker)
        
        scores = {}
        
        # Technical (30% weight)
        scores["ta"] = (ta.ta_score or 50.0) if ta else 50.0
        
        # Fundamental (25% weight)
        scores["fund"] = (fund.fundamental_score or 50.0) if fund else 50.0
        
        # Sentiment (15% weight)
        if sent and sent.sentiment_score is not None:
            scores["sent"] = (sent.sentiment_score + 1.0) / 2 * 100
        else:
            scores["sent"] = 50.0
        
        # Macro (15% weight)
        if macro and macro.macro_score is not None:
            scores["macro"] = macro.macro_score
        else:
            scores["macro"] = 50.0
        
        # Bull vs Bear debate adjudication (15% weight)
        if bull and bear:
            bull_c = bull.confidence
            bear_c = bear.confidence
            total = bull_c + bear_c
            if total > 0:
                debate_score = (bull_c / total) * 100
            else:
                debate_score = 50.0
        else:
            debate_score = 50.0
        scores["debate"] = debate_score
        
        # Get self-evolving dynamic weights
        dynamic_weights = self.state.memory.evolve_weights()
        
        # Base weight distribution (normalized)
        # We start with these and adjust them by the agent's historical accuracy
        base_w = {
            "ta": 0.30 * dynamic_weights.get("TechnicalAnalysis", 1.0),
            "fund": 0.25 * dynamic_weights.get("FundamentalAnalysis", 1.0),
            "sent": 0.15 * dynamic_weights.get("SentimentAnalysis", 1.0),
            "macro": 0.15 * dynamic_weights.get("MacroIntelligence", 1.0),
            "debate": 0.15 * ((dynamic_weights.get("BullAgent", 1.0) + dynamic_weights.get("BearAgent", 1.0)) / 2),
        }
        
        # Normalize weights so they sum to 1.0
        total_w = sum(base_w.values())
        w = {k: v / total_w for k, v in base_w.items()}
        
        # Weighted composite
        composite = (
            scores["ta"]     * w["ta"] +
            scores["fund"]   * w["fund"] +
            scores["sent"]   * w["sent"] +
            scores["macro"]  * w["macro"] +
            scores["debate"] * w["debate"]
        )
        
        # Risk adjustment: F-grade gets a penalty
        if risk and risk.risk_grade in ("D", "F"):
            composite *= 0.85
        if risk and risk.risk_grade == "A":
            composite = min(100, composite * 1.05)
        
        return round(composite, 1), scores

    def _action_from_score(self, score: float, holding_pnl: float, urgency: str) -> str:
        """Determine action from composite score with nuance."""
        # Strong buy zone
        if score >= 72 and urgency in ("HIGH", "CRITICAL"):
            return "BUY"
        if score >= 68:
            return "ADD"       # Add to existing position
        if score >= 58:
            return "HOLD"      # Keep — no action needed
        if score >= 48:
            return "WATCH"     # Monitor closely
        
        # If we're already profitable and score drops, trim
        if score < 45 and holding_pnl > 15:
            return "TRIM"      # Take some profits
        if score < 38:
            return "SELL"      # Exit
        
        return "HOLD"

    def _build_reasoning(
        self, ticker: str, action: str, composite: float, scores: dict
    ) -> str:
        """Build human-readable reasoning string."""
        ta   = self.state.technical_signals.get(ticker)
        fund = self.state.fundamental_signals.get(ticker)
        sent = self.state.sentiment_signals.get(ticker)
        risk = self.state.risk_metrics.get(ticker)
        bull = self.state.bull_theses.get(ticker)
        bear = self.state.bear_theses.get(ticker)
        holding = next((h for h in self.state.holdings if h.ticker == ticker), None)
        
        lines = [f"Action: {action} | Composite Score: {composite:.0f}/100"]
        lines.append("")
        
        # TA summary
        if ta:
            rsi_s = f"{ta.rsi_14:.1f}" if ta.rsi_14 is not None else "N/A"
            ema_trend = "EMA Bullish" if (ta.ema_50 and ta.ema_200 and ta.ema_50 > ta.ema_200) else "EMA Bearish"
            lines.append(f"TA [{scores.get('ta', 50):.0f}/100]: "
                        f"RSI={rsi_s} | Signal={ta.ta_signal} | Trend={ema_trend}")
        
        # Fundamental summary
        if fund:
            upside = None
            if fund.analyst_target and holding and holding.current_price:
                upside = ((fund.analyst_target - holding.current_price) / holding.current_price) * 100
            pe_s = f"{fund.pe_ratio:.1f}" if fund.pe_ratio else "N/A"
            up_s = (f"+{upside:.1f}%" if upside and upside > 0 else
                    f"{upside:.1f}%" if upside else "N/A")
            lines.append(f"Fundamental [{scores.get('fund', 50):.0f}/100]: "
                        f"P/E={pe_s} | Analyst: {(fund.analyst_rating or 'N/A').upper()} | "
                        f"Upside to Target: {up_s}")
        
        if sent:
            sent_sc = sent.sentiment_score
            sent_s = f"{sent_sc:+.2f}" if sent_sc is not None else "0.00"
            lines.append(f"Sentiment [{scores.get('sent', 50):.0f}/100]: "
                        f"{sent.sentiment_label} ({sent_s}) | "
                        f"{sent.news_count} articles analyzed")
        
        # Debate result
        if bull and bear:
            winner = "🐂 BULLS WIN" if bull.confidence > bear.confidence else "🐻 BEARS WIN"
            lines.append(f"⚡ Bull vs Bear Debate: {winner} "
                        f"(Bull {bull.confidence:.0%} vs Bear {bear.confidence:.0%})")
        
        if risk:
            sharpe_s = f"{risk.sharpe_ratio:.2f}" if risk.sharpe_ratio is not None else "N/A"
            var_s    = f"{risk.var_95:.2f}" if risk.var_95 is not None else "N/A"
            stop_s   = f"${risk.stop_loss_price:.2f}" if risk.stop_loss_price is not None else "N/A"
            lines.append(f"Risk Grade: {risk.risk_grade} | "
                        f"Sharpe={sharpe_s} | VaR95={var_s}% | Stop={stop_s}")
        
        # Top bull points
        if bull and bull.key_points:
            lines.append(f"🐂 Top Bull: {bull.key_points[0]}")
        
        # Top bear point
        if bear and bear.key_points:
            lines.append(f"🐻 Top Bear: {bear.key_points[0]}")
        
        return "\n".join(lines)

    async def run(self):
        self.log(f"🏆 [BLACKROCK STRATEGIST MODE] Synthesizing final recommendations...")
        self.log(f"  Analyzing {len(self.state.holdings)} positions across all 12 agent outputs...")
        
        for holding in self.state.holdings:
            ticker = holding.ticker
            current_price = holding.current_price or holding.avg_buy_price
            
            composite, scores = self._compute_composite_score(ticker)
            
            # Get urgency from time advisor
            existing_rec = self.state.recommendations.get(ticker)
            urgency = existing_rec.urgency if existing_rec else "MEDIUM"
            
            holding_pnl_pct = holding.unrealized_pnl_pct or 0
            action = self._action_from_score(composite, holding_pnl_pct, urgency)
            
            # Confidence from composite score
            confidence = composite / 100
            if action in ("SELL", "TRIM"):
                confidence = round(1.0 - composite / 100, 3)
            
            reasoning = self._build_reasoning(ticker, action, composite, scores)
            
            risk = self.state.risk_metrics.get(ticker)
            stop_loss = risk.stop_loss_price if risk else round(current_price * 0.92, 2)
            take_profit = risk.take_profit_price if risk else round(current_price * 1.20, 2)
            pos_size = risk.recommended_position_pct if risk else 10.0
            
            bull = self.state.bull_theses.get(ticker)
            target1 = bull.price_target if bull else take_profit
            target2 = round(target1 * 1.08, 2) if target1 else None
            
            # Build final recommendation
            rec = TradeRecommendation(
                ticker=ticker,
                action=action,
                confidence=round(confidence, 3),
                urgency=urgency,
                entry_window_start=existing_rec.entry_window_start if existing_rec else None,
                entry_window_end=existing_rec.entry_window_end if existing_rec else None,
                entry_price_low=existing_rec.entry_price_low if existing_rec else round(current_price * 0.99, 2),
                entry_price_high=existing_rec.entry_price_high if existing_rec else round(current_price * 1.01, 2),
                exit_target_1=round(target1, 2) if target1 else None,
                exit_target_2=target2,
                stop_loss=stop_loss,
                allocation_pct=pos_size,
                reasoning=reasoning,
                signals_summary={
                    "ta_score":    scores.get("ta", 50),
                    "fund_score":  scores.get("fund", 50),
                    "sent_score":  scores.get("sent", 50),
                    "macro_score": scores.get("macro", 50),
                    "debate_score": scores.get("debate", 50),
                    "composite":   composite,
                },
            )
            
            self.state.recommendations[ticker] = rec
            
            # Emoji for action
            emoji = {"BUY": "🟢", "ADD": "🔵", "HOLD": "⚪", "WATCH": "🟡",
                     "TRIM": "🟠", "SELL": "🔴"}.get(action, "⚪")
            
            tgt1_s = f"${target1:.2f}" if target1 else "N/A"
            stop_s  = f"${stop_loss:.2f}" if stop_loss else "N/A"
            self.log(
                f"  {ticker}: {action} | Confidence={confidence:.0%} | "
                f"Score={composite:.0f}/100 | "
                f"Entry ${rec.entry_price_low:.2f}-${rec.entry_price_high:.2f} | "
                f"Target {tgt1_s} | Stop {stop_s}"
            )
        
        self.state.completed_at = datetime.now().isoformat()
        self.log("✅ ALL RECOMMENDATIONS COMPLETE. Your agents have spoken.")
        self.log("=" * 60)
        self.log("SUMMARY:")
        for ticker, rec in self.state.recommendations.items():
            emoji = {"BUY": "🟢", "ADD": "🔵", "HOLD": "⚪", "WATCH": "🟡",
                     "TRIM": "🟠", "SELL": "🔴"}.get(rec.action, "⚪")
            self.log(f"  {emoji} {ticker}: {rec.action} @ {rec.confidence:.0%} confidence")
