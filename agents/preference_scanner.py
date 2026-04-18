"""
Agent 15: Preference Scanner
Scans stocks tailored to the user's chosen investment strategy.

Personas mapped from Fuck-coding Prompts repo (github.com/Fuck-coding/Prompts-):
  - GROWTH:    Prompt #1  — Goldman Sachs senior equity analyst framework
  - DIVIDEND:  Prompt #6  — Harvard $50B Endowment dividend income strategy  
  - REIT:      Prompt #6  — Harvard Endowment + income focus on real estate
  - VALUE:     Prompt #2  — Morgan Stanley VP DCF & valuation framework
  - MOMENTUM:  Prompt #8  — Renaissance Technologies quant/statistical edge
  - ALL:       Blended composite of all strategies
"""
import asyncio
from datetime import datetime, timedelta
from agents.base_agent import BaseAgent
from core.state import TradeRecommendation


# ── Stock Universes per Strategy ──────────────────────────────────────
UNIVERSES = {
    "GROWTH": [
        # Goldman Sachs Prompt #1: Revenue growth >15%, strong moat, expanding TAM
        ("AMD",   "Advanced Micro Devices",  "Technology"),
        ("AVGO",  "Broadcom",                "Technology"),
        ("SNOW",  "Snowflake",               "Technology"),
        ("CRWD",  "CrowdStrike",             "Technology"),
        ("DDOG",  "Datadog",                 "Technology"),
        ("SHOP",  "Shopify",                 "Technology"),
        ("MELI",  "MercadoLibre",            "Consumer"),
        ("PANW",  "Palo Alto Networks",      "Technology"),
        ("UBER",  "Uber Technologies",       "Technology"),
        ("LLY",   "Eli Lilly",               "Healthcare"),
    ],
    "DIVIDEND": [
        # Harvard Endowment Prompt #6: Dividend safety, consecutive growth, sustainability
        ("JNJ",   "Johnson & Johnson",       "Healthcare"),
        ("KO",    "Coca-Cola",               "Consumer"),
        ("PG",    "Procter & Gamble",        "Consumer"),
        ("PEP",   "PepsiCo",                 "Consumer"),
        ("ABBV",  "AbbVie",                  "Healthcare"),
        ("CVX",   "Chevron",                 "Energy"),
        ("VZ",    "Verizon",                 "Telecom"),
        ("T",     "AT&T",                    "Telecom"),
        ("IBM",   "IBM",                     "Technology"),
        ("MO",    "Altria Group",            "Consumer"),
        ("MMM",   "3M Company",              "Industrial"),
        ("D",     "Dominion Energy",         "Utilities"),
    ],
    "REIT": [
        # Harvard Endowment real estate income focus
        ("O",     "Realty Income Corp",      "Real Estate"),
        ("AMT",   "American Tower",          "Real Estate"),
        ("PLD",   "Prologis",                "Real Estate"),
        ("EQIX",  "Equinix",                 "Real Estate"),
        ("SPG",   "Simon Property Group",    "Real Estate"),
        ("DLR",   "Digital Realty Trust",    "Real Estate"),
        ("PSA",   "Public Storage",          "Real Estate"),
        ("WPC",   "W.P. Carey",              "Real Estate"),
        ("NNN",   "National Retail Props",   "Real Estate"),
        ("VICI",  "VICI Properties",         "Real Estate"),
    ],
    "VALUE": [
        # Morgan Stanley DCF Prompt #2: Undervalued vs intrinsic value
        ("BRK-B", "Berkshire Hathaway B",    "Financials"),
        ("BAC",   "Bank of America",         "Financials"),
        ("JPM",   "JPMorgan Chase",          "Financials"),
        ("WFC",   "Wells Fargo",             "Financials"),
        ("C",     "Citigroup",               "Financials"),
        ("GE",    "GE Aerospace",            "Industrial"),
        ("GM",    "General Motors",          "Consumer"),
        ("XOM",   "Exxon Mobil",             "Energy"),
        ("CVS",   "CVS Health",              "Healthcare"),
        ("MRK",   "Merck",                   "Healthcare"),
    ],
    "MOMENTUM": [
        # Renaissance Tech Prompt #8: Statistical edge, price momentum, short interest
        ("NVDA",  "NVIDIA",                  "Technology"),  # even if held, momentum check
        ("META",  "Meta Platforms",          "Technology"),
        ("TSLA",  "Tesla",                   "Consumer"),
        ("PLTR",  "Palantir",                "Technology"),
        ("COIN",  "Coinbase",                "Financials"),
        ("SMCI",  "Super Micro Computer",    "Technology"),
        ("ARM",   "Arm Holdings",            "Technology"),
        ("RBLX",  "Roblox",                  "Technology"),
        ("SOFI",  "SoFi Technologies",       "Financials"),
        ("RIVN",  "Rivian Automotive",       "Consumer"),
    ],
}

# Strategy personas (from the prompts repo)
PERSONAS = {
    "GROWTH":   "Goldman Sachs Senior Equity Analyst (Prompt #1)",
    "DIVIDEND": "Harvard $50B Endowment Fund — Dividend Income (Prompt #6)",
    "REIT":     "Harvard Endowment — Real Estate Income (Prompt #6)",
    "VALUE":    "Morgan Stanley VP — DCF & Valuation (Prompt #2)",
    "MOMENTUM": "Renaissance Technologies Quant Researcher (Prompt #8)",
    "ALL":      "Blended Strategy — Multi-Persona Composite",
}

# Key metrics each strategy weights most heavily
STRATEGY_WEIGHTS = {
    "GROWTH":   {"ta": 0.25, "fund": 0.50, "macro": 0.25, "min_rev_growth": 0.10},
    "DIVIDEND": {"ta": 0.15, "fund": 0.55, "macro": 0.30, "min_div_yield": 0.03},
    "REIT":     {"ta": 0.15, "fund": 0.50, "macro": 0.35, "min_div_yield": 0.04},
    "VALUE":    {"ta": 0.20, "fund": 0.60, "macro": 0.20, "max_pe": 20},
    "MOMENTUM": {"ta": 0.65, "fund": 0.15, "macro": 0.20, "min_rsi": 45},
    "ALL":      {"ta": 0.35, "fund": 0.40, "macro": 0.25},
}


class PreferenceScannerAgent(BaseAgent):
    name = "PreferenceScanner"
    description = "Scans stocks based on user's investment strategy preference using Fuck-coding Prompts personas."

    def _held_tickers(self) -> set:
        return {h.ticker.upper() for h in self.state.holdings}

    async def run(self):
        strategy = (self.state.settings.get("strategy", "ALL") or "ALL").upper()
        if strategy == "ALL":
            # Use all universes combined, deduplicated
            seen = set()
            universe = []
            for strat, stocks in UNIVERSES.items():
                for s in stocks:
                    if s[0] not in seen:
                        seen.add(s[0])
                        universe.append(s)
        else:
            universe = UNIVERSES.get(strategy, UNIVERSES["GROWTH"])

        persona  = PERSONAS.get(strategy, PERSONAS["ALL"])
        weights  = STRATEGY_WEIGHTS.get(strategy, STRATEGY_WEIGHTS["ALL"])
        held     = self._held_tickers()

        # Filter out held stocks (except MOMENTUM — you want to know if held ones have momentum)
        if strategy != "MOMENTUM":
            universe = [(t, n, s) for t, n, s in universe if t.upper() not in held]

        self.log(f"🎯 [{persona}]")
        self.log(f"   Strategy: {strategy} | Universe: {len(universe)} stocks | Held filtered: {len(held)}")

        results = []

        for ticker, name, sector in universe:
            try:
                quote = self.use_tool("get_live_price", ticker=ticker)
                price = quote.get("price") if quote else None
                if not price:
                    continue

                df = self.use_tool("fetch_ohlcv", ticker=ticker, period="6mo", interval="1d")
                if df is None or (hasattr(df, "empty") and df.empty):
                    continue

                fund = self.use_tool("get_fundamentals", ticker=ticker)
                returns = self.use_tool("calculate_returns", df=df)
                sharpe  = self.use_tool("compute_sharpe", returns=returns) or 0
                mdd     = self.use_tool("compute_max_drawdown", prices=df["Close"]) or -50

                close  = df["Close"]
                sma50  = close.rolling(50).mean().iloc[-1]
                sma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else sma50

                delta  = close.diff()
                gain   = delta.clip(lower=0).rolling(14).mean().iloc[-1]
                loss   = (-delta.clip(upper=0)).rolling(14).mean().iloc[-1]
                rsi    = 100 - (100 / (1 + gain / loss)) if loss and loss != 0 else 50

                pe           = fund.get("pe_ratio")
                fwd_pe       = fund.get("forward_pe")
                rev_growth   = fund.get("revenue_growth_yoy") or 0
                earn_growth  = fund.get("earnings_growth_yoy") or 0
                roe          = fund.get("roe") or 0
                div_yield    = fund.get("dividend_yield") or 0
                tgt          = fund.get("analyst_target")
                rtg          = fund.get("analyst_rating", "")
                peg          = fund.get("peg_ratio")
                debt_eq      = fund.get("debt_to_equity") or 0
                profit_margin= fund.get("profit_margin") or 0

                # ── TA Score ──────────────────────────────────────────
                ta = 50.0
                if price > sma50:    ta += 10
                if price > sma200:   ta += 10
                if sma50 > sma200:   ta += 10
                if 30 < rsi < 50:    ta += 15   # sweet spot
                elif rsi < 30:       ta += 20   # oversold
                elif rsi > 70:       ta -= 15
                if sharpe > 1.0:     ta += 10
                if mdd > -15:        ta += 5
                ta = max(0, min(100, ta))

                # ── Fundamental Score (strategy-aware) ────────────────
                fs = 50.0

                if strategy == "GROWTH":
                    # Goldman Sachs: Revenue growth, moat, EPS acceleration
                    if rev_growth > 0.20:   fs += 20
                    elif rev_growth > 0.10: fs += 12
                    if earn_growth > 0.15:  fs += 15
                    if roe > 0.20:          fs += 10
                    if pe and pe < 50:      fs += 5
                    if tgt and tgt > price: fs += min(15, (tgt-price)/price*60)

                elif strategy in ("DIVIDEND", "REIT"):
                    # Harvard Endowment: Dividend yield, payout sustainability, consecutive growth
                    if div_yield > 0.05:    fs += 25
                    elif div_yield > 0.03:  fs += 15
                    elif div_yield > 0.02:  fs += 8
                    if debt_eq < 1.0:       fs += 10   # low debt = sustainable dividend
                    if profit_margin > 0.10: fs += 10
                    if roe > 0.10:          fs += 8
                    if tgt and tgt > price: fs += min(10, (tgt-price)/price*40)

                elif strategy == "VALUE":
                    # Morgan Stanley DCF: PE vs fair value, PEG, P/B discount
                    if pe and pe < 12:          fs += 25
                    elif pe and pe < 18:        fs += 15
                    if peg and peg < 1.0:       fs += 20
                    if rev_growth > 0:          fs += 8
                    if roe > 0.12:              fs += 10
                    if tgt and tgt > price:
                        upside = (tgt - price) / price
                        if upside > 0.30:       fs += 20
                        elif upside > 0.15:     fs += 10

                elif strategy == "MOMENTUM":
                    # Renaissance: Statistical edge, price above MAs, volume surge
                    if rsi > 50 and price > sma50:  fs += 30
                    if price > sma200:              fs += 20
                    if sharpe > 1.5:               fs += 20
                    if earn_growth > 0.10:         fs += 10

                else:  # ALL
                    if tgt and tgt > price:    fs += min(15, (tgt-price)/price*60)
                    if rev_growth > 0.05:      fs += 10
                    if roe > 0.12:             fs += 8
                    if pe and 8 < pe < 35:     fs += 8

                fs = max(0, min(100, fs))

                macro_score = self.state.macro_data.macro_score if self.state.macro_data else 50.0
                composite   = (
                    ta * weights["ta"] +
                    fs * weights["fund"] +
                    macro_score * weights["macro"]
                )

                results.append({
                    "ticker": ticker, "name": name, "sector": sector,
                    "price": round(price, 2), "composite": round(composite, 1),
                    "ta_score": round(ta, 1), "fund_score": round(fs, 1),
                    "macro_score": round(macro_score, 1),
                    "rsi": round(rsi, 1), "sharpe": round(sharpe, 2),
                    "pe": pe, "fwd_pe": fwd_pe, "peg": peg,
                    "rev_growth": rev_growth, "earn_growth": earn_growth,
                    "div_yield": div_yield, "roe": roe, "debt_eq": debt_eq,
                    "analyst_target": tgt, "analyst_rating": rtg,
                    "strategy": strategy, "persona": persona,
                })

                self.log(f"  📊 {ticker}: Score={composite:.0f} | TA={ta:.0f} | Fund={fs:.0f} | RSI={rsi:.0f} | PE={pe}")

            except Exception as e:
                self.log(f"  ⚠️  {ticker}: {e}")
                continue

        # ── Top 5 ranked by composite ─────────────────────────────────
        top5 = sorted(results, key=lambda x: x["composite"], reverse=True)[:5]

        pref_recs = {}
        for rank, s in enumerate(top5, 1):
            ticker = s["ticker"]
            price  = s["price"]
            tgt    = s["analyst_target"]
            score  = s["composite"]

            entry_low  = round(price * 0.97, 2)
            entry_high = round(price * 1.02, 2)
            stop       = round(price * 0.91, 2)

            if tgt and tgt > price:
                target1 = round(tgt, 2)
                target2 = round(tgt * 1.10, 2)
            else:
                target1 = round(price * 1.22, 2)
                target2 = round(price * 1.38, 2)

            upside_pct = round((target1 - price) / price * 100, 1)

            # Hold duration by strategy
            if strategy == "DIVIDEND":
                hold = "12–36 months (Hold for dividend compounding + DRIP reinvestment)"
            elif strategy == "REIT":
                hold = "12–24 months (Income focus — hold through rate cycle)"
            elif strategy == "GROWTH":
                hold = "6–18 months (Ride earnings acceleration curve)"
            elif strategy == "VALUE":
                hold = "12–24 months (Patient value unlock — wait for rerating)"
            elif strategy == "MOMENTUM":
                hold = "1–3 months (Momentum play — trail stop aggressively)"
            else:
                hold = "6–12 months (Diversified strategy hold)"

            div_str = f"{s['div_yield']*100:.1f}%" if s["div_yield"] else "N/A"
            pe_str  = f"{s['pe']:.1f}" if s["pe"] else "N/A"
            rev_str = f"{s['rev_growth']*100:.1f}%" if s["rev_growth"] else "N/A"

            rec = TradeRecommendation(
                ticker=ticker,
                action="BUY",
                confidence=round(min(score, 95) / 100, 3),
                urgency="HIGH" if score >= 72 else "MEDIUM",
                entry_window_start=datetime.now().strftime("%Y-%m-%d"),
                entry_window_end=(datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
                entry_price_low=entry_low,
                entry_price_high=entry_high,
                exit_target_1=target1,
                exit_target_2=target2,
                stop_loss=stop,
                allocation_pct=round(min(20.0, score / 5), 1),
                reasoning=(
                    f"RANK #{rank} — {strategy} Strategy Pick\n"
                    f"Persona: {persona}\n"
                    f"Score: {score:.0f}/100 | Upside: +{upside_pct}%\n"
                    f"PE: {pe_str} | Rev Growth: {rev_str} | Div Yield: {div_str}\n"
                    f"Sharpe: {s['sharpe']:.2f} | RSI: {s['rsi']:.0f}\n"
                    f"Hold Duration: {hold}"
                ),
                signals_summary={
                    "ta_score":      s["ta_score"],
                    "fund_score":    s["fund_score"],
                    "macro_score":   s["macro_score"],
                    "composite":     score,
                    "upside_pct":    upside_pct,
                    "hold_duration": hold,
                    "rank":          rank,
                    "sector":        s["sector"],
                    "name":          s["name"],
                    "rsi":           s["rsi"],
                    "sharpe":        s["sharpe"],
                    "pe":            s["pe"],
                    "div_yield":     s["div_yield"],
                    "rev_growth":    s["rev_growth"],
                    "strategy":      strategy,
                    "persona":       persona,
                },
            )
            pref_recs[ticker] = rec
            self.log(
                f"  #{rank} {ticker} ({s['name']}) — BUY | Score={score:.0f} | "
                f"Target ${target1:.2f} (+{upside_pct}%) | Hold: {hold[:35]}..."
            )

        self.state.preference_recommendations = pref_recs
        self.log(f"✅ Preference scan complete — {len(pref_recs)} picks for strategy: {strategy}")
