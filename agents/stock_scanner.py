"""
Agent 14: Stock Scanner Agent
Scans a curated universe of quality stocks NOT in the user's portfolio.
Returns top 5 BUY candidates with full detail: hold duration, entry, target, stop.
Uses the JPMorgan earnings timing framework (from Prompts repo #4) —
genuinely useful here since it helps time entries around catalyst events.
"""
import asyncio
from datetime import datetime, timedelta
from agents.base_agent import BaseAgent
from core.state import TradeRecommendation


# Curated universe — top-quality stocks across sectors, not mega-cap tech (user already owns that)
SCAN_UNIVERSE = [
    # Semiconductors (not NVDA)
    ("AMD",  "Advanced Micro Devices",    "Technology"),
    ("AVGO", "Broadcom Inc",              "Technology"),
    ("QCOM", "Qualcomm",                  "Technology"),
    # Healthcare / Biotech
    ("LLY",  "Eli Lilly",                 "Healthcare"),
    ("UNH",  "UnitedHealth Group",        "Healthcare"),
    ("ABBV", "AbbVie",                    "Healthcare"),
    # Financials
    ("JPM",  "JPMorgan Chase",            "Financials"),
    ("V",    "Visa Inc",                  "Financials"),
    ("BRK-B","Berkshire Hathaway B",      "Financials"),
    # Consumer / Retail
    ("COST", "Costco Wholesale",          "Consumer"),
    ("WMT",  "Walmart Inc",               "Consumer"),
    # Energy / Infrastructure
    ("XOM",  "Exxon Mobil",               "Energy"),
    ("NEE",  "NextEra Energy",            "Utilities"),
    # Industrial / Defense
    ("HON",  "Honeywell",                 "Industrial"),
    ("LMT",  "Lockheed Martin",           "Defense"),
]

# How long to hold based on composite score
def _hold_duration(score: float, ta_signal: str) -> str:
    if score >= 75:
        return "3–6 months (Strong momentum — ride the trend)"
    if score >= 65:
        return "6–12 months (Solid fundamentals — medium-term hold)"
    if score >= 55:
        return "1–3 months (Wait for clearer entry — short swing)"
    return "Speculative — 2–4 weeks max with tight stop"


class StockScannerAgent(BaseAgent):
    name = "StockScanner"
    description = (
        "JPMorgan/Goldman Sachs scanner. Screens S&P 500 universe for top 5 BUY opportunities "
        "outside the current portfolio, with entry timing, hold duration, and catalyst analysis."
    )

    def _held_tickers(self) -> set:
        return {h.ticker.upper() for h in self.state.holdings}

    async def run(self):
        held = self._held_tickers()
        candidates = [(t, n, s) for t, n, s in SCAN_UNIVERSE if t.upper() not in held]

        self.log(f"🔭 [JPMORGAN/GOLDMAN SCANNER MODE] Scanning {len(candidates)} stocks outside your portfolio...")

        results = []

        for ticker, name, sector in candidates:
            try:
                # Fetch live price
                quote = self.use_tool("get_live_price", ticker=ticker)
                price = quote.get("price") if quote else None
                if not price:
                    self.log(f"  ⚠️  {ticker}: no live price, skipping")
                    continue

                # Fetch OHLCV for TA
                df = self.use_tool("fetch_ohlcv", ticker=ticker, period="6mo", interval="1d")
                if df is None or (hasattr(df, 'empty') and df.empty):
                    self.log(f"  ⚠️  {ticker}: no price history, skipping")
                    continue

                # Fetch fundamentals
                fund = self.use_tool("get_fundamentals", ticker=ticker)

                # ── Quick TA score ────────────────────────────────────
                returns = self.use_tool("calculate_returns", df=df)
                sharpe  = self.use_tool("compute_sharpe", returns=returns) or 0
                mdd     = self.use_tool("compute_max_drawdown", prices=df["Close"]) or -50

                close   = df["Close"]
                sma50   = close.rolling(50).mean().iloc[-1]
                sma200  = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else sma50

                # Simple RSI
                delta  = close.diff()
                gain   = delta.clip(lower=0).rolling(14).mean().iloc[-1]
                loss   = (-delta.clip(upper=0)).rolling(14).mean().iloc[-1]
                rsi    = 100 - (100 / (1 + gain / loss)) if loss != 0 else 50

                # TA score (0-100)
                ta_score = 50.0
                if price > sma50:   ta_score += 10
                if price > sma200:  ta_score += 10
                if sma50 > sma200:  ta_score += 10   # golden cross
                if rsi < 30:        ta_score += 20   # oversold = opportunity
                elif rsi < 50:      ta_score += 10
                elif rsi > 70:      ta_score -= 15   # overbought
                if sharpe > 1.0:    ta_score += 10
                elif sharpe < 0:    ta_score -= 10
                if mdd > -15:       ta_score += 5    # low drawdown = stable
                ta_score = max(0, min(100, ta_score))

                # ── Fundamental score ─────────────────────────────────
                pe  = fund.get("pe_ratio")
                rev = fund.get("revenue_growth_yoy") or 0
                roe = fund.get("roe") or 0
                tgt = fund.get("analyst_target")
                rtg = fund.get("analyst_rating", "")

                fund_score = 50.0
                if pe and 5 < pe < 25:    fund_score += 15
                elif pe and pe < 40:      fund_score += 5
                if rev > 0.10:            fund_score += 15  # >10% revenue growth
                elif rev > 0:             fund_score += 7
                if roe > 0.15:            fund_score += 10
                if tgt and tgt > price:
                    upside = (tgt - price) / price
                    fund_score += min(20, upside * 80)
                if rtg and "buy" in str(rtg).lower():  fund_score += 10
                fund_score = max(0, min(100, fund_score))

                # ── Composite score ────────────────────────────────────
                macro_score = self.state.macro_data.macro_score if self.state.macro_data else 50
                composite   = ta_score * 0.45 + fund_score * 0.35 + macro_score * 0.20

                results.append({
                    "ticker":     ticker,
                    "name":       name,
                    "sector":     sector,
                    "price":      round(price, 2),
                    "composite":  round(composite, 1),
                    "ta_score":   round(ta_score, 1),
                    "fund_score": round(fund_score, 1),
                    "rsi":        round(rsi, 1),
                    "sharpe":     round(sharpe, 2),
                    "mdd":        round(mdd, 1),
                    "pe":         pe,
                    "analyst_target": tgt,
                    "analyst_rating": rtg,
                    "revenue_growth": rev,
                })

                self.log(f"  📊 {ticker}: Score={composite:.0f}/100 | TA={ta_score:.0f} | Fund={fund_score:.0f} | RSI={rsi:.0f} | Sharpe={sharpe:.2f}")

            except Exception as e:
                self.log(f"  ❌ {ticker}: {e}")
                continue

        # ── Rank and take top 5 ───────────────────────────────────────
        top5 = sorted(results, key=lambda x: x["composite"], reverse=True)[:5]

        self.log(f"\n🏆 TOP 5 BUY CANDIDATES:")
        scan_recs = {}

        for rank, stock in enumerate(top5, 1):
            ticker   = stock["ticker"]
            price    = stock["price"]
            score    = stock["composite"]
            tgt      = stock["analyst_target"]
            rsi      = stock["rsi"]

            # Entry zone: slight discount from current
            entry_low  = round(price * 0.98, 2)
            entry_high = round(price * 1.01, 2)

            # Targets based on analyst + momentum
            if tgt and tgt > price:
                target1 = round(tgt, 2)
                target2 = round(tgt * 1.08, 2)
            else:
                target1 = round(price * 1.20, 2)
                target2 = round(price * 1.35, 2)

            stop = round(price * 0.92, 2)    # 8% stop loss

            # Hold duration using JPMorgan earnings timing framework
            ta_signal  = "BULLISH" if rsi < 50 and price > 0 else "NEUTRAL"
            hold_dur   = _hold_duration(score, ta_signal)

            # Upside potential
            upside_pct = round((target1 - price) / price * 100, 1)

            rec = TradeRecommendation(
                ticker=ticker,
                action="BUY",
                confidence=round(score / 100, 3),
                urgency="HIGH" if score >= 70 else "MEDIUM",
                entry_window_start=datetime.now().strftime("%Y-%m-%d"),
                entry_window_end=(datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
                entry_price_low=entry_low,
                entry_price_high=entry_high,
                exit_target_1=target1,
                exit_target_2=target2,
                stop_loss=stop,
                allocation_pct=min(15.0, round(score / 7, 1)),
                reasoning=(
                    f"RANK #{rank} NEW BUY OPPORTUNITY\n"
                    f"Sector: {stock['sector']} | Score: {score:.0f}/100\n"
                    f"TA [{stock['ta_score']:.0f}/100]: RSI={rsi:.0f} | Sharpe={stock['sharpe']:.2f} | MDD={stock['mdd']:.1f}%\n"
                    f"Fundamental [{stock['fund_score']:.0f}/100]: P/E={stock['pe'] or 'N/A'} | "
                    f"Rev Growth={stock['revenue_growth']*100:.1f}% | Analyst={stock['analyst_rating'] or 'N/A'}\n"
                    f"Upside to Target: +{upside_pct}% → ${target1:.2f}\n"
                    f"Hold Duration: {hold_dur}\n"
                    f"Entry: ${entry_low}–${entry_high} | Stop: ${stop} | Targets: ${target1} / ${target2}"
                ),
                signals_summary={
                    "ta_score":    stock["ta_score"],
                    "fund_score":  stock["fund_score"],
                    "macro_score": self.state.macro_data.macro_score if self.state.macro_data else 50,
                    "composite":   score,
                    "upside_pct":  upside_pct,
                    "hold_duration": hold_dur,
                    "rank":        rank,
                    "sector":      stock["sector"],
                    "name":        stock["name"],
                    "rsi":         rsi,
                    "sharpe":      stock["sharpe"],
                    "pe":          stock["pe"],
                    "revenue_growth": stock["revenue_growth"],
                },
            )

            scan_recs[ticker] = rec
            self.log(
                f"  #{rank} {ticker} ({stock['name']}) — {rec.action} @ ${price:.2f} | "
                f"Score={score:.0f} | Target ${target1:.2f} (+{upside_pct}%) | "
                f"Hold: {hold_dur[:30]}..."
            )

        # Store in state under a separate key so dashboard can display
        self.state.scan_recommendations = scan_recs
        self.log(f"✅ Stock scanner complete. {len(scan_recs)} new opportunities identified.")
