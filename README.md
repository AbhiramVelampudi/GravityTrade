# ⚡ GravityTrade — AI Stock Intelligence System

> **15-Agent MCP-powered portfolio analysis platform. Zero API keys. 100% scraping.**

---

## 🚀 Features

- **15 Elite Agents** running in dependency-ordered phases (sequential + parallel)
- **Institutional Personas**: Goldman Sachs, Citadel, BlackRock, Bridgewater, Harvard Endowment, Renaissance Technologies, Morgan Stanley
- **Investment Strategy Selector**: Growth / Dividend / REIT / Value / Momentum
- **Portfolio Editor**: Edit your holdings live from the dashboard
- **Top 5 New Buy Picks**: Scanned from a curated universe, not in your portfolio
- **Real-time WebSocket Dashboard**: Agent statuses, live logs, recommendations
- **Self-Evolving Memory**: Agent weights adjust based on historical accuracy
- **Zero API Keys**: 100% web scraping — yfinance, Finviz, FRED, Google News RSS

---

## 🧠 Agent Pipeline

| Phase | Agents |
|-------|--------|
| **Phase 1** (Sequential) | Orchestrator → Portfolio Ingestor → Market Data |
| **Phase 2** (Parallel) | Technical Analysis, Fundamental Analysis, Sentiment, Macro Intel |
| **Phase 3** (Parallel) | Bull Agent, Bear Agent, Pattern Recognition, Stock Scanner, Preference Scanner |
| **Phase 4** (Sequential) | Risk Manager → Time Advisor → Portfolio Strategist |

---

## ⚙️ Setup

```bash
# 1. Clone the repo
git clone https://github.com/AbhiramVelampudi/GravityTrade.git
cd GravityTrade

# 2. Install dependencies
pip install -r requirements.txt

# 3. Edit your portfolio
# Open data/portfolio.json and add your holdings, OR use the dashboard editor

# 4. Run the server
python run.py

# 5. Open the dashboard
# http://localhost:8080
```

---

## 📦 Requirements

```
fastapi uvicorn websockets
yfinance pandas pandas-ta numpy
requests beautifulsoup4 lxml feedparser
```

---

## 📊 Data Sources (Zero API Keys)

| Source | Data |
|--------|------|
| **yfinance** | Live prices, OHLCV, fundamentals fallback |
| **Finviz** | P/E, analyst targets, beta, fundamentals |
| **FRED** | 10Y/2Y Treasury yields, VIX |
| **Google News RSS** | Live news for sentiment analysis |

---

## 🎯 Investment Strategies

| Strategy | Persona | Universe |
|----------|---------|---------|
| 🚀 Growth | Goldman Sachs (Prompt #1) | CRWD, SNOW, DDOG, SHOP, LLY... |
| 💰 Dividend | Harvard Endowment (Prompt #6) | JNJ, KO, PG, ABBV, CVX... |
| 🏢 REIT | Harvard Endowment Real Estate | O, AMT, PLD, EQIX, PSA... |
| ⚖️ Value | Morgan Stanley DCF (Prompt #2) | BRK-B, BAC, JPM, MRK... |
| ⚡ Momentum | Renaissance Technologies (Prompt #8) | PLTR, COIN, SMCI, ARM... |

---

## ⚠️ Disclaimer

For informational purposes only. Not financial advice. Always do your own research.
