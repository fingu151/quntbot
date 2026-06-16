"""
quntbot ?꾩뿭 ?ㅼ젙
=================
紐⑤뱺 ?뚮씪誘명꽣(?먭툑쨌?먯젅瑜졖룻뙥??媛以묒튂 ??瑜??쒓납??紐⑥븘???뚯씪.

?먯튃:
- 留ㅻℓ ?숈옉???곹뼢 媛???レ옄??肄붾뱶 ?덉뿉 ?⑸퓣由ъ? 留먭퀬 ?ш린濡?紐⑥???
- ?섍꼍 ?섏〈(API ?? DB 寃쎈줈)? .env ?먯꽌 ?쎈뒗??
- 寃利앸맂 湲곕낯媛믪쓣 ?먮릺, 諛깊뀒?ㅽ듃 寃곌낵濡?議곗젙?쒕떎
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# .env ?먮룞 濡쒕뱶 (?놁뼱???먮윭 ????
load_dotenv()


def _csv_tuple(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())

# =============================================================================
# 寃쎈줈
# =============================================================================
ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
LOG_DIR = ROOT_DIR / "logs"
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "quntbot.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

# =============================================================================
# 留ㅻℓ 紐⑤뱶
# =============================================================================
TradeMode = Literal["PAPER", "LIVE"]
TRADE_MODE: TradeMode = os.getenv("TRADE_MODE", "PAPER")  # type: ignore

# =============================================================================
# KIS API
# =============================================================================
@dataclass(frozen=True)
class KISConfig:
    app_key: str = os.getenv("KIS_APP_KEY", "")
    app_secret: str = os.getenv("KIS_APP_SECRET", "")
    account_no: str = os.getenv("KIS_ACCOUNT_NO", "")
    account_product_code: str = os.getenv("KIS_ACCOUNT_PRODUCT_CODE", "01")
    paper_base_url: str = os.getenv(
        "KIS_PAPER_BASE_URL", "https://openapivts.koreainvestment.com:29443"
    )
    live_base_url: str = os.getenv(
        "KIS_LIVE_BASE_URL", "https://openapi.koreainvestment.com:9443"
    )
    quote_base_url: str = os.getenv(
        "KIS_QUOTE_BASE_URL",
        os.getenv(
            "KIS_PAPER_BASE_URL" if TRADE_MODE == "PAPER" else "KIS_LIVE_BASE_URL",
            "https://openapivts.koreainvestment.com:29443"
            if TRADE_MODE == "PAPER"
            else "https://openapi.koreainvestment.com:9443",
        ),
    )
    request_timeout_sec: int = int(os.getenv("KIS_REQUEST_TIMEOUT_SEC", "10"))
    token_cache_path: Path = Path(
        os.getenv("KIS_TOKEN_CACHE_PATH", str(DATA_DIR / "kis_token_paper.json"))
    )

    @property
    def base_url(self) -> str:
        return self.paper_base_url if TRADE_MODE == "PAPER" else self.live_base_url


KIS = KISConfig()

# =============================================================================
# ?붾젅洹몃옩
# =============================================================================
@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)


TELEGRAM = TelegramConfig()




@dataclass(frozen=True)
class BusanstockSignalConfig:
    poll_start_hour: int = int(os.getenv("BUSANSTOCK_SIGNAL_POLL_START_HOUR", "6"))
    poll_end_hour: int = int(os.getenv("BUSANSTOCK_SIGNAL_POLL_END_HOUR", "9"))


BUSANSTOCK_SIGNAL = BusanstockSignalConfig()


@dataclass(frozen=True)
class ResearchReportConfig:
    enabled: bool = os.getenv("RESEARCH_REPORT_ENABLED", "true").lower() not in (
        "0",
        "false",
        "no",
    )
    source: str = os.getenv("RESEARCH_REPORT_SOURCE", "hankyung_consensus")
    broker: str = os.getenv("RESEARCH_REPORT_BROKER", "한경 컨센서스")
    url: str = os.getenv("RESEARCH_REPORT_URL", "https://consensus.hankyung.com/")
    poll_start_hour: int = int(os.getenv("RESEARCH_REPORT_POLL_START_HOUR", "6"))
    poll_end_hour: int = int(os.getenv("RESEARCH_REPORT_POLL_END_HOUR", "9"))


RESEARCH_REPORT = ResearchReportConfig()

# =============================================================================
# OpenDART
# =============================================================================
@dataclass(frozen=True)
class DartConfig:
    api_key: str = os.getenv("DART_API_KEY", "")
    requests_per_minute: int = int(os.getenv("DART_REQUESTS_PER_MINUTE", "60"))
    daily_quota: int = int(os.getenv("DART_DAILY_QUOTA", "10000"))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


DART = DartConfig()

# =============================================================================
# 醫낅ぉ ?좊땲踰꾩뒪
# =============================================================================
@dataclass(frozen=True)
class UniverseConfig:
    # 肄붿뒪??/ 肄붿뒪???꾩껜 ?쒖옣???꾨낫 ?濡??ъ슜
    use_kospi: bool = True
    use_kosdaq: bool = True
    use_etf: bool = False
    # 理쒓렐 ?됯퇏 嫄곕옒?湲?湲곗??쇰줈 理쒖쥌 ?좏깮???쒖옣蹂??곸쐞 醫낅ぉ ??
    kospi_top_n: int = 400
    kosdaq_top_n: int = 200
    etf_top_n: int = 20
    # ?좊룞???꾪꽣: 理쒓렐 N ?곸뾽???됯퇏 嫄곕옒?湲?湲곗?
    liquidity_lookback_days: int = 5
    min_avg_trading_value: float = 5_000_000_000   # 50?듭썝
    # ?먮룞 ?쒖쇅 醫낅ぉ ?좏삎
    exclude_preferred: bool = True     # ?곗꽑二?(ticker ?앹옄由?!= '0')
    exclude_managed: bool = True       # 愿由ъ쥌紐?
    exclude_warning: bool = True       # ?ъ옄二쇱쓽쨌寃쎄퀬쨌?꾪뿕
    exclude_suspended: bool = True     # 嫄곕옒?뺤?
    exclude_unverifiable_status: bool = True  # ?곹깭 ?뺤씤 ?ㅽ뙣 ???좉퇋 留ㅼ닔 ?꾨낫 ?쒖쇅


UNIVERSE = UniverseConfig()

# =============================================================================
# ?⑺꽣 媛以묒튂 & ?먯닔 怨꾩궛
# =============================================================================
@dataclass(frozen=True)
class FactorConfig:
    value_points: float = 25.0
    quality_points: float = 25.0
    momentum_points: float = 20.0
    yield_points: float = 5.0
    technical_points: float = 15.0
    auxiliary_points: float = 10.0
    busanstock_auxiliary_share: float = 1 / 3
    investor_flow_auxiliary_share: float = 1 / 3
    research_report_auxiliary_share: float = 1 / 3

    # 紐⑤찘? 猷⑸갚 湲곌컙 (?곸뾽??
    momentum_lookback_days: int = 126   # ??6媛쒖썡

    # ?먯닔 怨꾩궛 諛⑹떇: "zscore" ?먮뒗 "rank"
    # rank keeps factor scores bounded when local DB z-score outliers dominate.
    scoring_method: Literal["zscore", "rank"] = "rank"

    @property
    def score_budget_total(self) -> float:
        return (
            self.value_points
            + self.quality_points
            + self.momentum_points
            + self.yield_points
            + self.technical_points
            + self.auxiliary_points
        )


FACTOR = FactorConfig()

# =============================================================================
# ?ы듃?대━??/ ?먭툑 愿由?
# =============================================================================
@dataclass(frozen=True)
class PortfolioConfig:
    # MVP 湲곕낯媛?(紐⑥쓽?ъ옄 1??湲곗?)
    initial_capital: float = 100_000_000  # 1?듭썝 (紐⑥쓽?ъ옄)

    # 蹂댁쑀 醫낅ぉ ??
    n_holdings: int = 30

    # 醫낅ぉ蹂?鍮꾩쨷 ("equal" = 洹좊벑 / "score_weighted" = ?먯닔 鍮꾨?)
    weighting: Literal["equal", "score_weighted"] = "score_weighted"
    min_position_weight: float = 0.03
    max_position_weight: float = 0.15

    # 醫낅ぉ??留ㅼ닔 媛??媛寃??꾪꽣: ?좊떦 湲덉븸 < 1二?媛寃⑹씠硫??먮룞 ?쒖쇅
    enforce_price_filter: bool = True
    max_abs_open_gap_pct: float = 0.20

    @property
    def per_position_cash(self) -> float:
        return self.initial_capital / self.n_holdings


PORTFOLIO = PortfolioConfig()

# =============================================================================
# 留ㅻ룄 洹쒖튃 (3以??덉쟾?μ튂)
# =============================================================================
@dataclass(frozen=True)
class ExitRulesConfig:
    # ?먯젅: 留ㅼ닔媛 ?鍮?-X% ?꾨떖 ??利됱떆 ?쒖옣媛 留ㅻ룄
    stop_loss_pct: float = -0.07   # -7%

    # ?몃젅?쇰쭅 ?ㅽ넲: 蹂댁쑀 ??理쒓퀬媛 ?鍮?-X% ?섎씫 ??留ㅻ룄
    trailing_stop_pct: float = -0.08  # -8%
    post_profit_trailing_stop_pct: float = -0.10  # -10%
    # Calendar days to block rebuying a ticker after a stop exit. 0 preserves prior behavior.
    stop_cooldown_days: int = 3
    profit_take_pct: float = 0.16
    profit_take_sell_fraction: float = 0.45
    breakeven_stop_pct: float = 0.0
    enable_atr_stop: bool = True
    atr_window: int = 14
    atr_multiplier: float = 2.2
    # True면 ATR 스톱 사용 가능 종목은 고정 -stop_loss_pct 손절을 적용하지 않고
    # ATR 스톱만으로 하방을 통제한다(완화). ATR 데이터가 없으면 고정 손절을 폴백으로 유지.
    # 기본 False = 기존 동작(고정 손절 + ATR 스톱 병행) 유지.
    atr_only_stop: bool = False

    # 由щ갭?곗떛: ?먯닔 ?섏쐞濡?諛?ㅻ굹硫?援먯껜 (Phase 2 ?먯닔 ?붿쭊怨??곕룞)
    use_rebalance_exit: bool = True


EXIT_RULES = ExitRulesConfig()


@dataclass(frozen=True)
class MarketRiskConfig:
    enable_overlay: bool = True
    rsi_window: int = 14
    rsi_overheat_threshold: float = 75.0
    one_market_overheat_cash_target: float = 0.15
    both_markets_overheat_cash_target: float = 0.25
    nasdaq_moderate_drop_pct: float = -0.02
    nasdaq_severe_drop_pct: float = -0.035
    nasdaq_moderate_cash_target: float = 0.20
    nasdaq_severe_cash_target: float = 0.35


MARKET_RISK = MarketRiskConfig()


@dataclass(frozen=True)
class MacroRiskConfig:
    enable_overlay: bool = True
    moderate_cash_target: float = 0.20
    severe_cash_target: float = 0.40
    max_cash_target: float = 0.50
    risk_on_buy_multiplier: float = 1.10
    severe_risk_on_buy_multiplier: float = 1.20
    intraday_dry_run_only: bool = True
    fred_api_key: str = os.getenv("FRED_API_KEY", "")


MACRO_RISK = MacroRiskConfig()


@dataclass(frozen=True)
class InverseEtfHedgeConfig:
    enabled: bool = os.getenv("INVERSE_ETF_HEDGE_ENABLED", "true").lower() not in (
        "0",
        "false",
        "no",
    )
    allowed_tickers: tuple[str, ...] = field(
        default_factory=lambda: _csv_tuple(os.getenv("INVERSE_ETF_ALLOWED_TICKERS", ""))
    )
    allow_leveraged: bool = os.getenv("INVERSE_ETF_ALLOW_LEVERAGED", "true").lower() not in (
        "0",
        "false",
        "no",
    )
    leveraged_tickers: tuple[str, ...] = field(
        default_factory=lambda: _csv_tuple(os.getenv("INVERSE_ETF_LEVERAGED_TICKERS", ""))
    )
    max_total_weight: float = float(os.getenv("INVERSE_ETF_MAX_TOTAL_WEIGHT", "0.15"))
    max_1x_weight: float = float(os.getenv("INVERSE_ETF_MAX_1X_WEIGHT", "0.10"))
    max_2x_weight: float = float(os.getenv("INVERSE_ETF_MAX_2X_WEIGHT", "0.05"))
    moderate_target_weight: float = float(os.getenv("INVERSE_ETF_MODERATE_TARGET_WEIGHT", "0.05"))
    severe_target_weight: float = float(os.getenv("INVERSE_ETF_SEVERE_TARGET_WEIGHT", "0.10"))
    severe_2x_target_weight: float = float(os.getenv("INVERSE_ETF_SEVERE_2X_TARGET_WEIGHT", "0.03"))
    overbought_rsi_threshold: float = float(os.getenv("INVERSE_ETF_OVERBOUGHT_RSI_THRESHOLD", "75"))
    severe_overbought_rsi_threshold: float = float(
        os.getenv("INVERSE_ETF_SEVERE_OVERBOUGHT_RSI_THRESHOLD", "80")
    )
    market_drop_threshold: float = float(os.getenv("INVERSE_ETF_MARKET_DROP_THRESHOLD", "-0.03"))
    severe_market_drop_threshold: float = float(
        os.getenv("INVERSE_ETF_SEVERE_MARKET_DROP_THRESHOLD", "-0.05")
    )
    require_market_confirmation: bool = os.getenv(
        "INVERSE_ETF_REQUIRE_MARKET_CONFIRMATION", "false"
    ).lower() in ("1", "true", "yes")
    max_holding_days: int = int(os.getenv("INVERSE_ETF_MAX_HOLDING_DAYS", "10"))
    stop_loss_pct: float = float(os.getenv("INVERSE_ETF_STOP_LOSS_PCT", "-0.07"))
    take_profit_pct: float = float(os.getenv("INVERSE_ETF_TAKE_PROFIT_PCT", "0.12"))


INVERSE_ETF = InverseEtfHedgeConfig()

# =============================================================================
# 由щ갭?곗떛 ?ㅼ?以?
# =============================================================================
@dataclass(frozen=True)
class RebalanceConfig:
    # ?뺢린 由щ갭?곗떛 二쇨린
    frequency: Literal["daily", "weekly", "monthly"] = "weekly"
    sell_rank_buffer: int = 40
    min_holding_trading_days: int = 0

    # ???쒖옉 ???먯닔 ?ш퀎???쒓컖 (HH:MM, KST)
    # Pre-market data sync time (HH:MM, KST)
    pre_market_sync_time: str = "08:40"

    # Recent calendar days to refresh before market open
    pre_market_sync_lookback_days: int = 30

    # Block new rebalance orders if today's pre-market sync failed or did not run
    require_pre_market_sync: bool = True

    # Block automated order execution unless the latest dry-run JSON report is clean.
    require_dry_run_preflight: bool = (
        os.getenv("REBALANCE_REQUIRE_DRY_RUN_PREFLIGHT", "true").lower()
        not in ("0", "false", "no")
    )
    dry_run_preflight_report_path: Path = Path(
        os.getenv(
            "REBALANCE_DRY_RUN_PREFLIGHT_REPORT_PATH",
            str(DATA_DIR / "dry_run_rebalance_latest.json"),
        )
    )

    # Daily rebalance time (HH:MM, KST)
    rebalance_time: str = "09:05"

    # ?대깽??湲곕컲 由щ갭?곗떛 (媛뺥븳 ?좏샇 ??利됱떆 ?ㅽ뻾)
    enable_event_driven: bool = True


REBALANCE = RebalanceConfig()

# =============================================================================
# ?댁쁺 ?덉쟾?μ튂 (?꾩닔)
# =============================================================================
@dataclass(frozen=True)
class SafetyConfig:
    # ?쇱씪 留ㅻℓ ?잛닔 ?쒕룄
    max_daily_buys: int = 30
    max_daily_sells: int = 30

    # ?쇱씪 ?먯떎 ?쒕룄 ?꾨떖 ???좉퇋 留ㅼ닔 以묐떒. ?꾪뿕 異뺤냼??留ㅻ룄??怨꾩냽 ?덉슜?쒕떎.
    daily_loss_limit_pct: float = -0.03  # -3%

    # 泥닿껐 ?ㅽ뙣 ???ъ떆???잛닔
    order_retry_count: int = 3
    order_retry_delay_sec: int = 2

    # 遊??ъ뒪泥댄겕 二쇨린 (遺?
    healthcheck_interval_min: int = 60


SAFETY = SafetyConfig()

# =============================================================================
# ?섏닔猷뙿룹꽭湲?(諛깊뀒?ㅽ듃 ?뺥솗?꾩슜)
# =============================================================================
@dataclass(frozen=True)
class CostConfig:
    # 留ㅼ닔쨌留ㅻ룄 ?섏닔猷?(KIS ?곸썒臾퇣 湲곗? ??0.015%)
    commission_rate: float = 0.00015

    # 嫄곕옒??(留ㅻ룄 ?쒖뿉留?, 2026-01-01 ?쒗뻾 湲곗?
    # 肄붿뒪?? 0.20% = 利앷텒嫄곕옒??0.05% + ?띿뼱珥뚰듅蹂꾩꽭 0.15%
    # 肄붿뒪?? 0.20% = 利앷텒嫄곕옒??0.20%
    tax_rate_kospi: float = 0.0020
    tax_rate_kosdaq: float = 0.0020

    # ?щ━?쇱? (?덉긽 泥닿껐媛 - ?ㅼ젣 泥닿껐媛) 異붿젙移?
    slippage_rate: float = 0.0010  # 0.1%


COST = CostConfig()

# =============================================================================
# 諛깊뀒?ㅽ듃
# =============================================================================
@dataclass(frozen=True)
class BacktestConfig:
    start_date: str = "2020-01-01"
    end_date: str = "2025-12-31"
    benchmark_ticker: str = "069500"  # KODEX 200 ETF (踰ㅼ튂留덊겕)


BACKTEST = BacktestConfig()

# =============================================================================
# 濡쒓퉭
# =============================================================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = LOG_DIR / "quntbot.log"


# =============================================================================
# 寃利?(import ???먮룞 ?ㅽ뻾)
# =============================================================================
def validate() -> list[str]:
    """?ㅼ젙 ?쇨???泥댄겕. 臾몄젣媛 ?덉쑝硫?寃쎄퀬 硫붿떆吏 由ъ뒪??諛섑솚."""
    warnings = []
    if TRADE_MODE == "LIVE" and not KIS.app_key:
        warnings.append("LIVE 紐⑤뱶?몃뜲 KIS_APP_KEY 媛 鍮꾩뼱?덉뒿?덈떎.")
    if not DART.enabled:
        warnings.append("DART_API_KEY is empty; quality factors will stay unavailable.")
    if DART.requests_per_minute <= 0 or DART.daily_quota <= 0:
        warnings.append("DART request limit must be greater than 0. Check .env.")
    if KIS.request_timeout_sec <= 0:
        warnings.append("KIS request timeout must be greater than 0. Check .env.")
    if PORTFOLIO.n_holdings <= 0:
        warnings.append("PORTFOLIO.n_holdings ??1 ?댁긽?댁뼱???⑸땲??")
    if not 0 < PORTFOLIO.min_position_weight <= PORTFOLIO.max_position_weight <= 1:
        warnings.append("PORTFOLIO position weights must satisfy 0 < min <= max <= 1.")
    if EXIT_RULES.stop_loss_pct >= 0:
        warnings.append("EXIT_RULES.stop_loss_pct ???뚯닔?ъ빞 ?⑸땲??")
    if EXIT_RULES.trailing_stop_pct >= 0:
        warnings.append("EXIT_RULES.trailing_stop_pct ???뚯닔?ъ빞 ?⑸땲??")
    if EXIT_RULES.post_profit_trailing_stop_pct >= 0:
        warnings.append("EXIT_RULES.post_profit_trailing_stop_pct must be negative.")
    if EXIT_RULES.profit_take_pct <= 0:
        warnings.append("EXIT_RULES.profit_take_pct must be positive.")
    if not 0 < EXIT_RULES.profit_take_sell_fraction < 1:
        warnings.append("EXIT_RULES.profit_take_sell_fraction must be between 0 and 1.")
    if EXIT_RULES.atr_window <= 0:
        warnings.append("EXIT_RULES.atr_window must be greater than 0.")
    if EXIT_RULES.atr_multiplier <= 0:
        warnings.append("EXIT_RULES.atr_multiplier must be greater than 0.")
    for name in (
        "one_market_overheat_cash_target",
        "both_markets_overheat_cash_target",
        "nasdaq_moderate_cash_target",
        "nasdaq_severe_cash_target",
    ):
        value = getattr(MARKET_RISK, name)
        if not 0 <= value <= 1:
            warnings.append(f"MARKET_RISK.{name} must be between 0 and 1.")
    for name in ("moderate_cash_target", "severe_cash_target", "max_cash_target"):
        value = getattr(MACRO_RISK, name)
        if not 0 <= value <= 1:
            warnings.append(f"MACRO_RISK.{name} must be between 0 and 1.")
    if MACRO_RISK.moderate_cash_target > MACRO_RISK.severe_cash_target:
        warnings.append("MACRO_RISK.moderate_cash_target must be <= severe_cash_target.")
    if MACRO_RISK.severe_cash_target > MACRO_RISK.max_cash_target:
        warnings.append("MACRO_RISK.severe_cash_target must be <= max_cash_target.")
    if MACRO_RISK.risk_on_buy_multiplier <= 0 or MACRO_RISK.severe_risk_on_buy_multiplier <= 0:
        warnings.append("MACRO_RISK buy multipliers must be positive.")
    for name in (
        "max_total_weight",
        "max_1x_weight",
        "max_2x_weight",
        "moderate_target_weight",
        "severe_target_weight",
        "severe_2x_target_weight",
    ):
        value = getattr(INVERSE_ETF, name)
        if not 0 <= value <= 1:
            warnings.append(f"INVERSE_ETF.{name} must be between 0 and 1.")
    if INVERSE_ETF.max_1x_weight + INVERSE_ETF.max_2x_weight > INVERSE_ETF.max_total_weight + 1e-9:
        warnings.append("INVERSE_ETF 1x/2x caps must not exceed max_total_weight.")
    if INVERSE_ETF.severe_2x_target_weight > INVERSE_ETF.max_2x_weight:
        warnings.append("INVERSE_ETF.severe_2x_target_weight must be <= max_2x_weight.")
    if INVERSE_ETF.market_drop_threshold < INVERSE_ETF.severe_market_drop_threshold:
        warnings.append("INVERSE_ETF.market_drop_threshold must be >= severe_market_drop_threshold.")
    if INVERSE_ETF.max_holding_days <= 0:
        warnings.append("INVERSE_ETF.max_holding_days must be greater than 0.")
    if INVERSE_ETF.stop_loss_pct >= 0:
        warnings.append("INVERSE_ETF.stop_loss_pct must be negative.")
    if INVERSE_ETF.take_profit_pct <= 0:
        warnings.append("INVERSE_ETF.take_profit_pct must be positive.")
    if MARKET_RISK.rsi_window <= 0:
        warnings.append("MARKET_RISK.rsi_window must be greater than 0.")
    if MARKET_RISK.nasdaq_severe_drop_pct > MARKET_RISK.nasdaq_moderate_drop_pct:
        warnings.append("MARKET_RISK.nasdaq_severe_drop_pct must be <= nasdaq_moderate_drop_pct.")
    if REBALANCE.sell_rank_buffer < PORTFOLIO.n_holdings:
        warnings.append("REBALANCE.sell_rank_buffer must be >= PORTFOLIO.n_holdings.")
    if abs(FACTOR.score_budget_total - 100.0) > 1e-9:
        warnings.append("FACTOR point budget must total 100.")
    auxiliary_share_total = (
        FACTOR.busanstock_auxiliary_share
        + FACTOR.investor_flow_auxiliary_share
        + FACTOR.research_report_auxiliary_share
    )
    if abs(auxiliary_share_total - 1.0) > 1e-9:
        warnings.append("FACTOR auxiliary shares must total 1.")
    return warnings


if __name__ == "__main__":
    # python config.py 濡?吏곸젒 ?ㅽ뻾 ???꾩옱 ?ㅼ젙 異쒕젰 + 寃利?
    import json

    snapshot = {
        "TRADE_MODE": TRADE_MODE,
        "DATABASE_URL": DATABASE_URL,
        "UNIVERSE": UNIVERSE.__dict__,
        "DART": DART.__dict__,
        "FACTOR": FACTOR.__dict__,
        "PORTFOLIO": {**PORTFOLIO.__dict__, "per_position_cash": PORTFOLIO.per_position_cash},
        "EXIT_RULES": EXIT_RULES.__dict__,
        "MARKET_RISK": MARKET_RISK.__dict__,
        "MACRO_RISK": MACRO_RISK.__dict__,
        "INVERSE_ETF": INVERSE_ETF.__dict__,
        "REBALANCE": REBALANCE.__dict__,
        "SAFETY": SAFETY.__dict__,
        "COST": COST.__dict__,
        "BACKTEST": BACKTEST.__dict__,
        "TELEGRAM_ENABLED": TELEGRAM.enabled,
    }
    print(json.dumps(snapshot, indent=2, ensure_ascii=False, default=str))

    issues = validate()
    if issues:
        print("\n[寃쎄퀬]")
        for w in issues:
            print(f"  - {w}")
    else:
        print("\n[OK] ?ㅼ젙 ?쇨????듦낵")

