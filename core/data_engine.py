"""
core/data_engine.py — 100% SCRAPING ENGINE. ZERO API KEYS.

Data Sources (all free, no registration, no keys):
  Quotes/OHLCV:    yfinance (scrapes Yahoo Finance)
  Fundamentals:    Finviz scraper + yfinance .info
  Macro data:      FRED direct CSV URLs (St. Louis Fed)
  News/Sentiment:  Google News RSS (no key, ever)
  VIX/Yields:      yfinance (^VIX, ^TNX, ^IRX) + FRED fallback
"""
import io
import logging
import time
import random
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("DataEngine")

# ── One shared session with realistic browser headers ──────────
_session = requests.Session()
_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})

def _get(url: str, params: dict = None, timeout: int = 10) -> Optional[requests.Response]:
    try:
        time.sleep(random.uniform(0.1, 0.3))   # polite delay
        r = _session.get(url, params=params or {}, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        logger.debug(f"GET {url[:80]}: {e}")
        return None


# ─────────────────────────────────────────────────────────────
#  LIVE QUOTE — yfinance (scrapes Yahoo Finance internally)
# ─────────────────────────────────────────────────────────────
def get_realtime_quote(ticker: str) -> Dict[str, Any]:
    """
    Get live price via yfinance (no API key — it scrapes Yahoo Finance).
    Falls back to Finviz scrape if yfinance is blocked.
    """
    # 1. yfinance fast_info (fastest path)
    try:
        import yfinance as yf
        fi = yf.Ticker(ticker).fast_info
        price = getattr(fi, "last_price", None)
        if price and float(price) > 0:
            return {
                "ticker": ticker,
                "price":      float(price),
                "open":       getattr(fi, "open", None),
                "day_high":   getattr(fi, "day_high", None),
                "day_low":    getattr(fi, "day_low", None),
                "prev_close": getattr(fi, "previous_close", None),
                "source":     "yfinance",
            }
    except Exception as e:
        logger.debug(f"yfinance quote {ticker}: {e}")

    # 2. Finviz scraper fallback
    try:
        price = _scrape_finviz_price(ticker)
        if price:
            return {"ticker": ticker, "price": price, "source": "finviz"}
    except Exception as e:
        logger.debug(f"Finviz quote {ticker}: {e}")

    return {"ticker": ticker, "price": None, "source": "unavailable"}


def _scrape_finviz_price(ticker: str) -> Optional[float]:
    """Scrape current price from Finviz ticker page."""
    url = f"https://finviz.com/quote.ashx?t={ticker}&ty=c&ta=1&p=d"
    r = _get(url)
    if not r:
        return None
    soup = BeautifulSoup(r.text, "lxml")
    # Finviz shows price in a table cell with class 'snapshot-td2'
    for cell in soup.select("td.snapshot-td2"):
        txt = cell.get_text(strip=True)
        try:
            val = float(txt.replace(",", ""))
            if 0.01 < val < 100000:
                return val
        except Exception:
            pass
    return None


# ─────────────────────────────────────────────────────────────
#  OHLCV — yfinance (no key)
# ─────────────────────────────────────────────────────────────
def get_ohlcv(ticker: str, period_days: int = 180) -> Optional[Any]:
    """Fetch OHLCV DataFrame — yfinance only, no keys required."""
    try:
        import yfinance as yf
        period_str = (
            "5d"   if period_days <= 7   else
            "1mo"  if period_days <= 35  else
            "3mo"  if period_days <= 95  else
            "6mo"  if period_days <= 200 else
            "1y"   if period_days <= 370 else
            "2y"
        )
        df = yf.Ticker(ticker).history(period=period_str, interval="1d")
        if not df.empty:
            df.index = df.index.tz_localize(None)
            logger.info(f"[yfinance] {ticker}: {len(df)} bars ({period_str})")
            return df
    except Exception as e:
        logger.warning(f"yfinance OHLCV {ticker}: {e}")
    return None


# ─────────────────────────────────────────────────────────────
#  FUNDAMENTALS — Finviz scraper + yfinance .info fallback
# ─────────────────────────────────────────────────────────────
def get_fundamentals(ticker: str) -> Dict[str, Any]:
    """
    Scrape fundamentals from Finviz (no key).
    Falls back to yfinance .info.
    """
    result = {"ticker": ticker}

    # 1. Finviz scraper (best data, no key)
    try:
        fv = _scrape_finviz_fundamentals(ticker)
        if fv:
            result.update(fv)
            result["source_fundamentals"] = "finviz"
            logger.info(f"[Finviz] {ticker}: P/E={fv.get('pe_ratio')} Target=${fv.get('analyst_target')}")
    except Exception as e:
        logger.debug(f"Finviz fundamentals {ticker}: {e}")

    # 2. yfinance .info fallback / supplement
    if not result.get("pe_ratio"):
        try:
            import yfinance as yf
            info = yf.Ticker(ticker).info
            def sf(k):
                v = info.get(k)
                return float(v) if v is not None else None
            result.update({
                "pe_ratio":             sf("trailingPE"),
                "forward_pe":           sf("forwardPE"),
                "peg_ratio":            sf("pegRatio"),
                "price_to_book":        sf("priceToBook"),
                "price_to_sales":       sf("priceToSalesTrailing12Months"),
                "debt_to_equity":       sf("debtToEquity"),
                "roe":                  sf("returnOnEquity"),
                "revenue_growth_yoy":   sf("revenueGrowth"),
                "earnings_growth_yoy":  sf("earningsGrowth"),
                "profit_margin":        sf("profitMargins"),
                "free_cash_flow":       sf("freeCashflow"),
                "market_cap":           sf("marketCap"),
                "analyst_target":       sf("targetMeanPrice"),
                "analyst_rating":       info.get("recommendationKey"),
                "sector":               info.get("sector"),
                "source_fundamentals":  "yfinance",
            })
        except Exception as e:
            logger.warning(f"yfinance fundamentals {ticker}: {e}")

    return result


def _scrape_finviz_fundamentals(ticker: str) -> Optional[Dict]:
    """
    Scrape Finviz snapshot table for key fundamental metrics.
    Returns dict of values, no API key needed.
    """
    url = f"https://finviz.com/quote.ashx?t={ticker}"
    r = _get(url)
    if not r:
        return None

    soup = BeautifulSoup(r.text, "lxml")

    # Finviz snapshot: alternating label/value cells
    cells = soup.select("td.snapshot-td2-cp, td.snapshot-td2")
    data = {}
    labels = []
    for cell in cells:
        labels.append(cell.get_text(strip=True))

    # Build label→value map (label then value alternate)
    kv = {}
    for i in range(0, len(labels) - 1, 2):
        kv[labels[i]] = labels[i + 1]

    def parse(key: str) -> Optional[float]:
        v = kv.get(key, "")
        if not v or v in ("-", "N/A", ""):
            return None
        v = v.replace("%", "").replace(",", "").replace("B", "e9").replace("M", "e6")
        try:
            return float(v)
        except Exception:
            return None

    return {
        "pe_ratio":             parse("P/E"),
        "forward_pe":           parse("Forward P/E"),
        "peg_ratio":            parse("PEG"),
        "price_to_book":        parse("P/B"),
        "price_to_sales":       parse("P/S"),
        "debt_to_equity":       parse("Debt/Eq"),
        "roe":                  parse("ROE"),
        "revenue_growth_yoy":   _pct(parse("Sales Q/Q")),
        "earnings_growth_yoy":  _pct(parse("EPS Q/Q")),
        "profit_margin":        _pct(parse("Profit Margin")),
        "analyst_target":       parse("Target Price"),
        "analyst_rating":       kv.get("Recom", None),
        "beta":                 parse("Beta"),
        "52w_high":             parse("52W High"),
        "52w_low":              parse("52W Low"),
        "market_cap":           parse("Market Cap"),
    }

def _pct(v: Optional[float]) -> Optional[float]:
    """Convert percentage points to decimal (e.g. 15.3 → 0.153)."""
    return round(v / 100, 4) if v is not None else None


# ─────────────────────────────────────────────────────────────
#  MACRO DATA — FRED direct CSV (zero API key) + yfinance
# ─────────────────────────────────────────────────────────────
def get_macro() -> Dict[str, Any]:
    """
    Fetch macro data:
    - Yields (10Y, 2Y): FRED DGS10 / DGS2 direct CSV
    - VIX, SPX, DXY:    yfinance
    Zero API keys used.
    """
    macro = {}

    # ── Yield Curve from FRED (no key, direct CSV URL) ───────
    try:
        import pandas as pd
        def fetch_fred_series(series_id: str) -> Optional[float]:
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
            r = _get(url)
            if not r:
                return None
            df = pd.read_csv(io.StringIO(r.text), na_values=["."])
            df = df.dropna()
            if df.empty:
                return None
            return float(df.iloc[-1, 1])

        yield_10y = fetch_fred_series("DGS10")
        yield_2y  = fetch_fred_series("DGS2")
        vix_fred  = fetch_fred_series("VIXCLS")   # CBOE VIX daily close

        if yield_10y:
            macro["yield_10y"] = yield_10y
        if yield_2y:
            macro["yield_2y"] = yield_2y
        if yield_10y and yield_2y:
            macro["yield_curve_spread"] = round(yield_10y - yield_2y, 3)
        if vix_fred:
            macro["vix"] = vix_fred

        logger.info(f"[FRED] 10Y={yield_10y} 2Y={yield_2y} Spread={macro.get('yield_curve_spread')} VIX={vix_fred}")
    except Exception as e:
        logger.warning(f"FRED macro: {e}")

    # ── VIX + SPX + DXY via yfinance ─────────────────────────
    try:
        import yfinance as yf

        def quick_price(sym: str) -> Optional[float]:
            try:
                fi = yf.Ticker(sym).fast_info
                p = getattr(fi, "last_price", None)
                return float(p) if p else None
            except Exception:
                return None

        def monthly_change(sym: str) -> Optional[float]:
            try:
                h = yf.Ticker(sym).history(period="1mo")
                if h.empty:
                    return None
                return round((h["Close"].iloc[-1] - h["Close"].iloc[0]) / h["Close"].iloc[0] * 100, 2)
            except Exception:
                return None

        # Only fill in if FRED didn't provide
        if not macro.get("vix"):
            macro["vix"] = quick_price("^VIX")

        sp500 = quick_price("^GSPC")
        sp_chg = monthly_change("^GSPC")
        macro["sp500_current"] = sp500
        macro["sp500_1m_change"] = sp_chg
        macro["sp500_trend"] = (
            "UP"       if (sp_chg or 0) > 1  else
            "DOWN"     if (sp_chg or 0) < -1 else
            "SIDEWAYS"
        )
        macro["dollar_index"] = quick_price("DX-Y.NYB")

        # Fill yield data from yfinance if FRED failed
        if not macro.get("yield_10y"):
            macro["yield_10y"] = quick_price("^TNX")
        if not macro.get("yield_2y"):
            macro["yield_2y"] = quick_price("^IRX")
        if macro.get("yield_10y") and macro.get("yield_2y") and not macro.get("yield_curve_spread"):
            macro["yield_curve_spread"] = round(macro["yield_10y"] - macro["yield_2y"], 3)

    except Exception as e:
        logger.warning(f"yfinance macro: {e}")

    return macro


# ─────────────────────────────────────────────────────────────
#  NEWS — Google News RSS (zero API key, ever)
# ─────────────────────────────────────────────────────────────
def get_news(ticker: str, max_items: int = 20) -> List[Dict]:
    """
    Fetch news via Google News RSS feed.
    Completely free, no API key, no rate limits that matter.
    """
    articles = []

    # 1. Google News RSS — best free source
    try:
        import feedparser
        # Both company name and ticker queries
        queries = [ticker]
        for q in queries:
            url = f"https://news.google.com/rss/search?q={q}+stock+investing&hl=en-US&gl=US&ceid=US:en"
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_items]:
                title = entry.get("title", "")
                if title and title not in [a["title"] for a in articles]:
                    articles.append({
                        "title":     title,
                        "summary":   entry.get("summary", "")[:300],
                        "source":    entry.get("source", {}).get("title", "Google News"),
                        "published": entry.get("published", ""),
                        "link":      entry.get("link", ""),
                    })
            if len(articles) >= max_items:
                break
        if articles:
            logger.info(f"[Google News RSS] {ticker}: {len(articles)} articles")
            return articles[:max_items]
    except Exception as e:
        logger.debug(f"Google News RSS {ticker}: {e}")

    # 2. yfinance news fallback
    try:
        import yfinance as yf
        news = yf.Ticker(ticker).news or []
        for item in news[:max_items]:
            content = item.get("content", {})
            title = content.get("title", item.get("title", ""))
            if title:
                articles.append({
                    "title":     title,
                    "summary":   content.get("summary", "")[:300],
                    "source":    "Yahoo Finance",
                    "published": content.get("pubDate", ""),
                })
        logger.info(f"[yfinance news] {ticker}: {len(articles)} articles")
    except Exception as e:
        logger.debug(f"yfinance news {ticker}: {e}")

    return articles[:max_items]


# ─────────────────────────────────────────────────────────────
#  SCRAPING HEALTH CHECK
# ─────────────────────────────────────────────────────────────
def check_scraper_health() -> Dict[str, str]:
    """Check which data sources are reachable."""
    status = {}

    # yfinance
    try:
        import yfinance as yf
        p = yf.Ticker("AAPL").fast_info.last_price
        status["yfinance"] = "OK" if p else "NO_DATA"
    except Exception:
        status["yfinance"] = "DOWN"

    # Finviz
    try:
        p = _scrape_finviz_price("AAPL")
        status["finviz"] = "OK" if p else "BLOCKED"
    except Exception:
        status["finviz"] = "DOWN"

    # FRED
    try:
        r = _get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10", timeout=5)
        status["fred"] = "OK" if r else "DOWN"
    except Exception:
        status["fred"] = "DOWN"

    # Google News RSS
    try:
        import feedparser
        f = feedparser.parse("https://news.google.com/rss/search?q=AAPL+stock&hl=en-US&gl=US&ceid=US:en")
        status["google_news_rss"] = "OK" if f.entries else "NO_ENTRIES"
    except Exception:
        status["google_news_rss"] = "DOWN"

    return status
