"""
PortfolioState — The shared state object passed between all 13 agents.
Acts as the MCP context store.
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from datetime import datetime


@dataclass
class PerformanceMemory:
    """Self-Evolving Memory System: Tracks agent accuracy and adjusts weights."""
    historical_accuracy: Dict[str, float] = field(default_factory=lambda: {
        "TechnicalAnalysis": 0.5,
        "FundamentalAnalysis": 0.5,
        "SentimentAnalysis": 0.5,
        "MacroIntelligence": 0.5,
        "BullAgent": 0.5,
        "BearAgent": 0.5,
    })
    total_trades_evaluated: int = 0
    successful_trades: int = 0
    win_rate: float = 0.0
    last_evaluation_date: Optional[str] = None
    
    def evolve_weights(self) -> Dict[str, float]:
        """Dynamically adjust agent weighting based on their historical accuracy."""
        total_acc = sum(self.historical_accuracy.values()) or 1.0
        return {k: v / total_acc for k, v in self.historical_accuracy.items()}


@dataclass
class Holding:
    ticker: str
    name: str
    shares: float
    avg_buy_price: float
    sector: str
    currency: str = "USD"
    current_price: Optional[float] = None
    market_value: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None


@dataclass
class TechnicalSignals:
    ticker: str
    rsi_14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
    ema_9: Optional[float] = None
    ema_21: Optional[float] = None
    ema_50: Optional[float] = None
    ema_200: Optional[float] = None
    atr_14: Optional[float] = None
    obv: Optional[float] = None
    vwap: Optional[float] = None
    volume_ratio: Optional[float] = None  # current vs 20d avg
    ta_score: Optional[float] = None       # 0-100 composite
    ta_signal: Optional[str] = None        # BUY | SELL | HOLD | WATCH


@dataclass
class FundamentalSignals:
    ticker: str
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    peg_ratio: Optional[float] = None
    price_to_book: Optional[float] = None
    price_to_sales: Optional[float] = None
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    roe: Optional[float] = None            # Return on equity
    revenue_growth_yoy: Optional[float] = None
    earnings_growth_yoy: Optional[float] = None
    profit_margin: Optional[float] = None
    free_cash_flow: Optional[float] = None
    market_cap: Optional[float] = None
    analyst_target: Optional[float] = None
    analyst_rating: Optional[str] = None
    fundamental_score: Optional[float] = None  # 0-100
    fundamental_signal: Optional[str] = None


@dataclass
class SentimentSignals:
    ticker: str
    sentiment_score: Optional[float] = None   # -1 to +1
    sentiment_label: Optional[str] = None     # POSITIVE | NEGATIVE | NEUTRAL
    news_count: int = 0
    top_headlines: List[str] = field(default_factory=list)
    reddit_sentiment: Optional[float] = None
    social_volume_change: Optional[float] = None
    sentiment_signal: Optional[str] = None


@dataclass
class MacroData:
    fed_rate: Optional[float] = None
    inflation_rate: Optional[float] = None
    gdp_growth: Optional[float] = None
    unemployment: Optional[float] = None
    yield_10y: Optional[float] = None
    yield_2y: Optional[float] = None
    yield_curve_spread: Optional[float] = None  # 10Y - 2Y
    sp500_trend: Optional[str] = None           # UP | DOWN | SIDEWAYS
    vix: Optional[float] = None
    dollar_index: Optional[float] = None
    macro_score: Optional[float] = None         # 0-100 market health
    macro_signal: Optional[str] = None


@dataclass
class BullBearThesis:
    ticker: str
    side: str  # "bull" | "bear"
    confidence: float = 0.0
    key_points: List[str] = field(default_factory=list)
    price_target: Optional[float] = None
    timeframe: Optional[str] = None
    risks: List[str] = field(default_factory=list)


@dataclass
class PatternAlert:
    ticker: str
    pattern_name: str
    pattern_type: str     # "bullish" | "bearish" | "neutral"
    reliability: float    # 0-1
    description: str
    price_target: Optional[float] = None
    detected_at: Optional[float] = None   # price when detected


@dataclass
class RiskMetrics:
    ticker: str
    var_95: Optional[float] = None        # Value at Risk 95%
    var_99: Optional[float] = None        # Value at Risk 99%
    max_drawdown: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    beta: Optional[float] = None
    volatility_annual: Optional[float] = None
    recommended_position_pct: Optional[float] = None
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    risk_grade: Optional[str] = None       # A | B | C | D | F


@dataclass
class TradeRecommendation:
    ticker: str
    action: str                           # BUY | SELL | HOLD | TRIM | ADD
    confidence: float = 0.0              # 0-1
    urgency: str = "LOW"                 # LOW | MEDIUM | HIGH | CRITICAL
    entry_window_start: Optional[str] = None
    entry_window_end: Optional[str] = None
    entry_price_low: Optional[float] = None
    entry_price_high: Optional[float] = None
    exit_target_1: Optional[float] = None
    exit_target_2: Optional[float] = None
    stop_loss: Optional[float] = None
    allocation_pct: Optional[float] = None
    reasoning: str = ""
    signals_summary: Dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class PortfolioState:
    """Master state object shared across all 13 agents via MCP context."""
    
    # Raw holdings from user
    holdings: List[Holding] = field(default_factory=list)
    settings: Dict[str, Any] = field(default_factory=dict)
    
    # Market data (populated by Agent 3)
    price_data: Dict[str, Any] = field(default_factory=dict)  # ticker -> OHLCV DataFrame info
    
    # Agent outputs
    technical_signals: Dict[str, TechnicalSignals] = field(default_factory=dict)
    fundamental_signals: Dict[str, FundamentalSignals] = field(default_factory=dict)
    sentiment_signals: Dict[str, SentimentSignals] = field(default_factory=dict)
    macro_data: Optional[MacroData] = None
    
    # Debate outputs
    bull_theses: Dict[str, BullBearThesis] = field(default_factory=dict)
    bear_theses: Dict[str, BullBearThesis] = field(default_factory=dict)
    
    # Pattern alerts
    pattern_alerts: Dict[str, List[PatternAlert]] = field(default_factory=dict)
    
    # Risk metrics
    risk_metrics: Dict[str, RiskMetrics] = field(default_factory=dict)
    portfolio_var: Optional[float] = None
    portfolio_sharpe: Optional[float] = None
    
    # Final recommendations
    recommendations: Dict[str, TradeRecommendation] = field(default_factory=dict)
    
    # Top 5 new BUY candidates (not in portfolio) — from StockScanner
    scan_recommendations: Dict[str, TradeRecommendation] = field(default_factory=dict)

    # Strategy-preference-based picks (Growth/Dividend/REIT/Value/Momentum)
    preference_recommendations: Dict[str, TradeRecommendation] = field(default_factory=dict)
    
    # Self-Evolving memory
    memory: PerformanceMemory = field(default_factory=PerformanceMemory)
    
    # Agent run tracking
    agent_statuses: Dict[str, str] = field(default_factory=dict)   # agent_name -> status
    agent_logs: Dict[str, List[str]] = field(default_factory=dict)  # agent_name -> log lines
    
    # Run metadata
    run_id: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    total_portfolio_value: Optional[float] = None
    total_cost_basis: Optional[float] = None
    total_pnl: Optional[float] = None
    total_pnl_pct: Optional[float] = None
