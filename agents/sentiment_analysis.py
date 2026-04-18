"""
Agent 6: Sentiment Analysis Agent
Fetches news headlines and scores them with lexicon-based FinBERT-style analysis.
Uses a robust keyword-weighted approach (no GPU required) + yfinance news.
"""
import asyncio
import re
from typing import List, Dict
from agents.base_agent import BaseAgent
from core.state import SentimentSignals


# Financial domain sentiment lexicon (FinBERT-inspired keywords)
BULLISH_TERMS = {
    "strong": 2, "growth": 2, "beat": 3, "exceeded": 3, "record": 2,
    "surge": 3, "rally": 2, "upgrade": 3, "outperform": 3, "buy": 2,
    "bullish": 3, "profit": 2, "revenue": 1, "earnings beat": 4,
    "raised guidance": 4, "dividend increase": 3, "buyback": 2,
    "innovation": 1, "partnership": 1, "acquisition": 1, "contract": 1,
    "expansion": 2, "momentum": 2, "gains": 2, "rises": 2, "jumps": 2,
    "soars": 3, "climbs": 2, "breakthrough": 3, "milestone": 2, "ai": 1,
    "artificial intelligence": 2, "generative": 1, "demand": 1,
}

BEARISH_TERMS = {
    "miss": -3, "missed": -3, "disappoints": -3, "downgrade": -3,
    "sell": -2, "bearish": -3, "loss": -2, "decline": -2, "drop": -2,
    "falls": -2, "plunges": -3, "slumps": -3, "crash": -4, "warning": -2,
    "lawsuit": -2, "regulatory": -1, "fine": -2, "investigation": -2,
    "layoffs": -2, "recession": -3, "inflation": -1, "rate hike": -2,
    "debt": -1, "bankruptcy": -5, "fraud": -4, "scandal": -3,
    "cut guidance": -4, "lowered guidance": -4, "disappointing": -3,
    "weak": -2, "sluggish": -2, "underperform": -3, "concern": -1,
    "risk": -1, "volatile": -1, "uncertainty": -2, "tariff": -2,
}


def score_headline(headline: str) -> float:
    """Score a single headline from -1.0 to +1.0."""
    text = headline.lower()
    score = 0
    total_weight = 0
    
    for term, weight in BULLISH_TERMS.items():
        if term in text:
            score += weight
            total_weight += abs(weight)
    
    for term, weight in BEARISH_TERMS.items():
        if term in text:
            score += weight
            total_weight += abs(weight)
    
    if total_weight == 0:
        return 0.0
    
    return max(-1.0, min(1.0, score / (total_weight * 0.5)))


def label_score(score: float) -> str:
    if score > 0.15:  return "POSITIVE"
    if score < -0.15: return "NEGATIVE"
    return "NEUTRAL"


class SentimentAnalysisAgent(BaseAgent):
    name = "SentimentAnalysis"
    description = "Analyzes news sentiment using financial NLP lexicon scoring."

    async def run(self):
        self.log(f"🗞️ Running sentiment analysis on {len(self.state.holdings)} holdings...")
        
        for holding in self.state.holdings:
            ticker = holding.ticker
            self.log(f"  ↳ Fetching news for {ticker}...")
            
            articles = self.use_tool("fetch_news_headlines", ticker=ticker, max_articles=20)
            
            if not articles:
                self.log(f"  ⚠️ No news found for {ticker}", level="warning")
                self.state.sentiment_signals[ticker] = SentimentSignals(
                    ticker=ticker,
                    sentiment_score=0.0,
                    sentiment_label="NEUTRAL",
                    sentiment_signal="HOLD"
                )
                continue
            
            # Score all headlines
            scores = []
            top_headlines = []
            for article in articles:
                title = article.get("title", "")
                summary = article.get("summary", "")
                combined = f"{title} {summary}"
                s = score_headline(combined)
                scores.append(s)
                if title:
                    top_headlines.append(title[:120])
            
            if not scores:
                avg_score = 0.0
            else:
                # Weighted average: recent articles get higher weight
                weights = [1.0 + (i * 0.1) for i in range(len(scores))]
                weights.reverse()
                weighted_sum = sum(s * w for s, w in zip(scores, weights))
                total_w = sum(weights)
                avg_score = weighted_sum / total_w if total_w > 0 else 0.0
                avg_score = round(max(-1.0, min(1.0, avg_score)), 4)
            
            label = label_score(avg_score)
            
            # Map to trading signal
            if avg_score > 0.3:   signal = "BUY"
            elif avg_score > 0.1: signal = "WATCH"
            elif avg_score < -0.3: signal = "SELL"
            elif avg_score < -0.1: signal = "CAUTION"
            else:                   signal = "HOLD"
            
            # Positive/negative count breakdown
            pos_count = sum(1 for s in scores if s > 0.1)
            neg_count = sum(1 for s in scores if s < -0.1)
            
            self.state.sentiment_signals[ticker] = SentimentSignals(
                ticker=ticker,
                sentiment_score=avg_score,
                sentiment_label=label,
                news_count=len(articles),
                top_headlines=top_headlines[:5],
                sentiment_signal=signal,
            )
            
            self.log(
                f"  ✅ {ticker}: Sentiment={avg_score:+.3f} [{label}] | "
                f"Bullish:{pos_count} Bearish:{neg_count} | Signal={signal}"
            )
        
        self.log("✅ Sentiment analysis complete.")
