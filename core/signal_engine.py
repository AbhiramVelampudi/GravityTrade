"""
core/signal_engine.py — Smart Money Signals. Zero API keys.
Sources: SEC EDGAR Form 4, OpenInsider, yfinance options, Finviz short interest, StockAnalysis EPS
"""
import io, logging, time, random
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("SignalEngine")

_s = requests.Session()
_s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
})

def _get(url, timeout=10):
    try:
        time.sleep(random.uniform(0.1, 0.25))
        r = _s.get(url, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        logger.debug(f"GET {url[:70]}: {e}")
        return None


# ── INSIDER TRADING (OpenInsider — no key) ────────────────────────────────
def get_insider_signal(ticker: str) -> Dict[str, Any]:
    """
    Scrape OpenInsider for recent insider BUY transactions.
    Cluster buying by insiders = strongest forward alpha signal.
    """
    result = {"ticker": ticker, "insider_score": 50.0, "insider_buys": 0,
              "insider_sells": 0, "insider_net_value": 0, "insider_signal": "NEUTRAL",
              "recent_trades": [], "source": "openinsider"}
    try:
        url = (f"http://openinsider.com/screener?s={ticker}&o=&pl=&ph=&ll=&lh="
               f"&fd=90&fdr=&td=0&tdr=&fdlyl=&fdlyh=&daysago=&xp=1&xs=1"
               f"&vl=25&vh=&ocl=&och=&sic1=-1&sortcol=0&cnt=20&page=1")
        r = _get(url)
        if not r:
            return result
        soup = BeautifulSoup(r.text, "lxml")
        rows = soup.select("table.tinytable tbody tr")
        buys = 0; sells = 0; net_val = 0
        trades = []
        for row in rows[:15]:
            cells = [c.get_text(strip=True) for c in row.find_all("td")]
            if len(cells) < 11:
                continue
            ttype = cells[5]   # P=Purchase, S=Sale
            try:
                val_str = cells[10].replace("$","").replace(",","").replace("+","")
                val = float(val_str) if val_str else 0
            except Exception:
                val = 0
            if "P" in ttype or "Buy" in ttype:
                buys += 1
                net_val += val
                trades.append({"type":"BUY","title":cells[4],"value":val,"date":cells[1]})
            elif "S" in ttype:
                sells += 1
                net_val -= val
                trades.append({"type":"SELL","title":cells[4],"value":val,"date":cells[1]})

        score = 50.0
        if buys >= 3 and net_val > 500000:   score = 88.0   # cluster buy = very bullish
        elif buys >= 2 and net_val > 100000: score = 74.0
        elif buys >= 1:                      score = 63.0
        if sells > buys * 2:                 score -= 20.0
        score = max(10, min(95, score))

        signal = "STRONG_BUY" if score >= 80 else "BUY" if score >= 65 else \
                 "SELL" if score <= 30 else "NEUTRAL"

        result.update({
            "insider_score":     round(score, 1),
            "insider_buys":      buys,
            "insider_sells":     sells,
            "insider_net_value": round(net_val, 0),
            "insider_signal":    signal,
            "recent_trades":     trades[:5],
        })
        logger.info(f"[Insider] {ticker}: {buys}B/{sells}S net=${net_val:,.0f} → {signal}")
    except Exception as e:
        logger.warning(f"Insider signal {ticker}: {e}")
    return result


# ── OPTIONS SENTIMENT (P/C ratio via yfinance) ────────────────────────────
def get_options_signal(ticker: str) -> Dict[str, Any]:
    """
    Put/Call ratio: low P/C = bullish positioning; high P/C = fear/bearish.
    Unusual call volume = institutional accumulation signal.
    """
    result = {"ticker": ticker, "pc_ratio": None, "options_score": 50.0,
              "options_signal": "NEUTRAL", "total_call_oi": 0, "total_put_oi": 0}
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        exps = t.options
        if not exps:
            return result

        # Use nearest expiry
        chain = t.option_chain(exps[0])
        calls = chain.calls
        puts  = chain.puts

        call_oi = int(calls["openInterest"].sum()) if "openInterest" in calls.columns else 0
        put_oi  = int(puts["openInterest"].sum())  if "openInterest" in puts.columns else 0
        call_vol = int(calls["volume"].fillna(0).sum()) if "volume" in calls.columns else 0
        put_vol  = int(puts["volume"].fillna(0).sum())  if "volume" in puts.columns else 0

        total_call = call_oi + call_vol
        total_put  = put_oi + put_vol
        pc = round(total_put / total_call, 3) if total_call > 0 else 1.0

        score = 50.0
        if pc < 0.5:    score = 80.0   # very bullish options flow
        elif pc < 0.7:  score = 68.0
        elif pc < 1.0:  score = 55.0
        elif pc < 1.5:  score = 40.0
        else:           score = 25.0   # extreme fear / put buying

        signal = "BULLISH" if score >= 70 else "BEARISH" if score <= 35 else "NEUTRAL"
        result.update({
            "pc_ratio":      pc,
            "options_score": round(score, 1),
            "options_signal": signal,
            "total_call_oi": total_call,
            "total_put_oi":  total_put,
        })
        logger.info(f"[Options] {ticker}: P/C={pc} → {signal}")
    except Exception as e:
        logger.debug(f"Options signal {ticker}: {e}")
    return result


# ── SHORT INTEREST (Finviz) ────────────────────────────────────────────────
def get_short_signal(ticker: str) -> Dict[str, Any]:
    """
    High short interest + price momentum = potential short squeeze.
    """
    result = {"ticker": ticker, "short_float_pct": None, "short_score": 50.0,
              "short_signal": "NEUTRAL", "days_to_cover": None}
    try:
        url = f"https://finviz.com/quote.ashx?t={ticker}"
        r = _get(url)
        if not r:
            return result
        soup = BeautifulSoup(r.text, "lxml")
        cells = soup.select("td.snapshot-td2-cp, td.snapshot-td2")
        labels = [c.get_text(strip=True) for c in cells]
        kv = {labels[i]: labels[i+1] for i in range(0, len(labels)-1, 2)}

        def pf(k):
            v = kv.get(k,"")
            try: return float(v.replace("%","").replace(",",""))
            except: return None

        short_float = pf("Short Float")    # e.g. 12.5 = 12.5%
        short_ratio = pf("Short Ratio")    # days to cover
        recom       = kv.get("Recom","")

        score = 50.0
        squeeze_signal = "NEUTRAL"
        if short_float:
            if short_float > 30:   score = 72.0; squeeze_signal = "HIGH_SQUEEZE_RISK"
            elif short_float > 20: score = 65.0; squeeze_signal = "MODERATE_SQUEEZE"
            elif short_float < 5:  score = 55.0; squeeze_signal = "LOW_SHORT"

        result.update({
            "short_float_pct": short_float,
            "days_to_cover":   short_ratio,
            "short_score":     round(score, 1),
            "short_signal":    squeeze_signal,
            "analyst_recom":   recom,
        })
        logger.info(f"[Short] {ticker}: {short_float}% float short, DTC={short_ratio}")
    except Exception as e:
        logger.debug(f"Short signal {ticker}: {e}")
    return result


# ── EARNINGS CALENDAR (yfinance) ──────────────────────────────────────────
def get_earnings_signal(ticker: str) -> Dict[str, Any]:
    """
    Days to next earnings + EPS beat/miss history.
    Don't buy within 5 days of earnings blind — high uncertainty.
    """
    result = {"ticker": ticker, "days_to_earnings": None, "earnings_score": 60.0,
              "earnings_signal": "UNKNOWN", "last_eps_surprise_pct": None}
    try:
        import yfinance as yf
        t   = yf.Ticker(ticker)
        cal = t.calendar
        info = t.info

        if isinstance(cal, dict):
            ed = cal.get("Earnings Date") or cal.get("earnings_date")
            if ed:
                if hasattr(ed, "__iter__") and not isinstance(ed, str):
                    ed = list(ed)[0]
                if hasattr(ed, "date"):
                    ed = ed.date()
                days = (ed - datetime.now().date()).days
                result["days_to_earnings"] = days

                if 0 <= days <= 5:
                    result["earnings_score"]  = 35.0   # high uncertainty window
                    result["earnings_signal"] = "AVOID_EARNINGS_RISK"
                elif 6 <= days <= 14:
                    result["earnings_score"]  = 55.0
                    result["earnings_signal"] = "PRE_EARNINGS"
                elif days > 14:
                    result["earnings_score"]  = 68.0
                    result["earnings_signal"] = "SAFE_WINDOW"

        # EPS surprise history
        surp = info.get("earningsSurprise") or info.get("earningsQuarterlyGrowth")
        if surp:
            result["last_eps_surprise_pct"] = round(float(surp)*100, 1)
            if float(surp) > 0.05:
                result["earnings_score"] = min(85, result["earnings_score"] + 15)
            elif float(surp) < -0.05:
                result["earnings_score"] = max(20, result["earnings_score"] - 15)

        logger.info(f"[Earnings] {ticker}: {result['days_to_earnings']}d to earnings → {result['earnings_signal']}")
    except Exception as e:
        logger.debug(f"Earnings signal {ticker}: {e}")
    return result


# ── SECTOR MOMENTUM (ETF relative strength vs SPY) ────────────────────────
SECTOR_ETFS = {
    "Technology":             "XLK",
    "Healthcare":             "XLV",
    "Financials":             "XLF",
    "Energy":                 "XLE",
    "Consumer Discretionary": "XLY",
    "Consumer Staples":       "XLP",
    "Industrials":            "XLI",
    "Real Estate":            "XLRE",
    "Utilities":              "XLU",
    "Communication Services": "XLC",
    "Materials":              "XLB",
}

def get_sector_momentum(sector: str) -> Dict[str, Any]:
    """Sector ETF momentum vs SPY = institutional money rotation signal."""
    result = {"sector": sector, "sector_score": 50.0, "sector_signal": "NEUTRAL",
              "etf_1m_return": None, "spy_1m_return": None}
    try:
        import yfinance as yf
        etf = SECTOR_ETFS.get(sector, "SPY")

        def one_month_return(sym):
            h = yf.Ticker(sym).history(period="1mo")
            if h.empty: return None
            return round((h["Close"].iloc[-1] - h["Close"].iloc[0]) / h["Close"].iloc[0] * 100, 2)

        etf_ret = one_month_return(etf)
        spy_ret = one_month_return("SPY")

        if etf_ret is not None and spy_ret is not None:
            rel = etf_ret - spy_ret
            score = 50 + rel * 4   # +1% outperformance = +4 score points
            score = max(10, min(90, score))
            signal = "STRONG" if score >= 70 else "WEAK" if score <= 35 else "NEUTRAL"
            result.update({
                "sector_score":  round(score, 1),
                "sector_signal": signal,
                "etf_1m_return": etf_ret,
                "spy_1m_return": spy_ret,
                "relative_strength": round(rel, 2),
            })
            logger.info(f"[Sector] {sector} ({etf}): {etf_ret:+.1f}% vs SPY {spy_ret:+.1f}% → {signal}")
    except Exception as e:
        logger.debug(f"Sector momentum {sector}: {e}")
    return result


# ── COMPOSITE SMART MONEY SCORE ───────────────────────────────────────────
def get_smart_money_score(ticker: str, sector: str = "Technology") -> Dict[str, Any]:
    """
    Combines insider, options, short squeeze, earnings, and sector signals
    into one institutional-grade composite score.
    """
    insider  = get_insider_signal(ticker)
    options  = get_options_signal(ticker)
    short    = get_short_signal(ticker)
    earnings = get_earnings_signal(ticker)
    sect     = get_sector_momentum(sector)

    w_insider  = 0.35
    w_options  = 0.25
    w_earnings = 0.20
    w_sector   = 0.20

    composite = (
        insider["insider_score"]   * w_insider  +
        options["options_score"]   * w_options  +
        earnings["earnings_score"] * w_earnings +
        sect["sector_score"]       * w_sector
    )

    # Squeeze bonus: high short + bullish options = squeeze catalyst
    if (short.get("short_float_pct") or 0) > 20 and options["options_score"] > 60:
        composite = min(95, composite + 8)

    signal = ("STRONG_BUY"  if composite >= 78 else
              "BUY"          if composite >= 63 else
              "WATCH"        if composite >= 50 else
              "AVOID")

    return {
        "ticker":          ticker,
        "smart_score":     round(composite, 1),
        "smart_signal":    signal,
        "insider":         insider,
        "options":         options,
        "short":           short,
        "earnings":        earnings,
        "sector":          sect,
    }
