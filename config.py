"""
quntbot 전역 설정
=================
모든 파라미터(자금·손절률·팩터 가중치 등)를 한곳에 모아둔 파일.

원칙:
- 매매 동작에 영향 가는 숫자는 코드 안에 흩뿌리지 말고 여기로 모은다
- 환경 의존(API 키, DB 경로)은 .env 에서 읽는다
- 검증된 기본값을 두되, 백테스트 결과로 조정한다
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# .env 자동 로드 (없어도 에러 안 남)
load_dotenv()

# =============================================================================
# 경로
# =============================================================================
ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
LOG_DIR = ROOT_DIR / "logs"
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "quntbot.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

# =============================================================================
# 매매 모드
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
        "KIS_QUOTE_BASE_URL", "https://openapi.koreainvestment.com:9443"
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
# 텔레그램
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
class TelegramSignalConfig:
    # MTProto 자격증명 (my.telegram.org 에서 발급)
    api_id: int = int(os.getenv("TELEGRAM_API_ID", "0"))
    api_hash: str = os.getenv("TELEGRAM_API_HASH", "")
    # 읽을 채널 username 또는 invite link (예: "morning_brief_channel")
    channel: str = os.getenv("TELEGRAM_SIGNAL_CHANNEL", "")
    # 팩터 점수에서 텔레그램 신호 가중치
    signal_weight: float = float(os.getenv("TELEGRAM_SIGNAL_WEIGHT", "0.5"))
    # 폴링: 장 시작 전 몇 시부터 채널을 확인할지 (KST)
    poll_start_hour: int = 6
    poll_end_hour: int = 9
    # 한 번 조회 시 가져올 최근 메시지 수
    fetch_limit: int = int(os.getenv("TELEGRAM_SIGNAL_FETCH_LIMIT", "20"))

    @property
    def enabled(self) -> bool:
        return bool(self.api_id and self.api_hash and self.channel)


TELEGRAM_SIGNAL = TelegramSignalConfig()


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
# 종목 유니버스
# =============================================================================
@dataclass(frozen=True)
class UniverseConfig:
    # 코스피 / 코스닥 전체 시장을 후보 풀로 사용
    use_kospi: bool = True
    use_kosdaq: bool = True
    # 최근 평균 거래대금 기준으로 최종 선택할 시장별 상위 종목 수
    kospi_top_n: int = 400
    kosdaq_top_n: int = 200
    # 유동성 필터: 최근 N 영업일 평균 거래대금 기준
    liquidity_lookback_days: int = 5
    min_avg_trading_value: float = 5_000_000_000   # 50억원
    # 자동 제외 종목 유형
    exclude_preferred: bool = True     # 우선주 (ticker 끝자리 != '0')
    exclude_managed: bool = True       # 관리종목
    exclude_warning: bool = True       # 투자주의·경고·위험
    exclude_suspended: bool = True     # 거래정지
    exclude_unverifiable_status: bool = True  # 상태 확인 실패 시 신규 매수 후보 제외


UNIVERSE = UniverseConfig()

# =============================================================================
# 팩터 가중치 & 점수 계산
# =============================================================================
@dataclass(frozen=True)
class FactorConfig:
    # 가치 팩터 (점수 ↑ = 저평가)
    value_weight: float = 1.0 + (0.25 / 3)
    # 퀄리티 팩터 (점수 ↑ = 우량) — ROE(EPS/BPS) 기반
    quality_weight: float = 1.0 + (0.25 / 3)
    # 모멘텀 팩터 (점수 ↑ = 강한 추세)
    momentum_weight: float = 1.0 + (0.25 / 3)
    # 배당수익률 팩터 (점수 ↑ = 고배당). 기존 0.5의 절반을 핵심 3팩터에 재배분한다.
    yield_weight: float = 0.25
    # 텔레그램 모닝 신호 팩터 (점수 ↑ = 강한 수혜 신호)
    telegram_weight: float = 0.5
    # Busanstock 뉴스/컨센서스 보조 팩터. 기존 퀀트 점수를 살짝만 보정한다.
    busanstock_weight: float = 0.3
    # 투자자별 수급 보조 팩터. 개인 단독 매수/외국인·기관 매도는 감점한다.
    investor_flow_weight: float = 0.3
    # 국내외 증권사 리서치 리포트 보조 팩터. 의견·목표가 변화 기반으로 작게 반영한다.
    research_report_weight: float = 0.25

    # 모멘텀 룩백 기간 (영업일)
    momentum_lookback_days: int = 126   # 약 6개월

    # 점수 계산 방식: "zscore" 또는 "rank"
    # rank keeps factor scores bounded when local DB z-score outliers dominate.
    scoring_method: Literal["zscore", "rank"] = "rank"


FACTOR = FactorConfig()

# =============================================================================
# 포트폴리오 / 자금 관리
# =============================================================================
@dataclass(frozen=True)
class PortfolioConfig:
    # MVP 기본값 (모의투자 1억 기준)
    initial_capital: float = 100_000_000  # 1억원 (모의투자)

    # 보유 종목 수
    n_holdings: int = 20

    # 종목별 비중 ("equal" = 균등 / "score_weighted" = 점수 비례)
    weighting: Literal["equal", "score_weighted"] = "score_weighted"
    min_position_weight: float = 0.03
    max_position_weight: float = 0.15

    # 종목당 매수 가능 가격 필터: 할당 금액 < 1주 가격이면 자동 제외
    enforce_price_filter: bool = True
    max_abs_open_gap_pct: float = 0.20

    @property
    def per_position_cash(self) -> float:
        return self.initial_capital / self.n_holdings


PORTFOLIO = PortfolioConfig()

# =============================================================================
# 매도 규칙 (3중 안전장치)
# =============================================================================
@dataclass(frozen=True)
class ExitRulesConfig:
    # 손절: 매수가 대비 -X% 도달 시 즉시 시장가 매도
    stop_loss_pct: float = -0.05   # -5%

    # 트레일링 스톱: 보유 후 최고가 대비 -X% 하락 시 매도
    trailing_stop_pct: float = -0.10  # -10%
    # Calendar days to block rebuying a ticker after a stop exit. 0 preserves prior behavior.
    stop_cooldown_days: int = 0
    profit_take_pct: float = 0.20
    profit_take_sell_fraction: float = 0.50
    breakeven_stop_pct: float = 0.0

    # 리밸런싱: 점수 하위로 밀려나면 교체 (Phase 2 점수 엔진과 연동)
    use_rebalance_exit: bool = True


EXIT_RULES = ExitRulesConfig()

# =============================================================================
# 리밸런싱 스케줄
# =============================================================================
@dataclass(frozen=True)
class RebalanceConfig:
    # 정기 리밸런싱 주기
    frequency: Literal["daily", "weekly", "monthly"] = "weekly"
    sell_rank_buffer: int = 30
    min_holding_trading_days: int = 2

    # 장 시작 전 점수 재계산 시각 (HH:MM, KST)
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

    # 이벤트 기반 리밸런싱 (강한 신호 시 즉시 실행)
    enable_event_driven: bool = True


REBALANCE = RebalanceConfig()

# =============================================================================
# 운영 안전장치 (필수)
# =============================================================================
@dataclass(frozen=True)
class SafetyConfig:
    # 일일 매매 횟수 한도
    max_daily_buys: int = 10
    max_daily_sells: int = 10

    # 일일 손실 한도 도달 시 당일 모든 매매 중단
    daily_loss_limit_pct: float = -0.03  # -3%

    # 체결 실패 시 재시도 횟수
    order_retry_count: int = 3
    order_retry_delay_sec: int = 2

    # 봇 헬스체크 주기 (분)
    healthcheck_interval_min: int = 60


SAFETY = SafetyConfig()

# =============================================================================
# 수수료·세금 (백테스트 정확도용)
# =============================================================================
@dataclass(frozen=True)
class CostConfig:
    # 매수·매도 수수료 (KIS 영웅문S 기준 약 0.015%)
    commission_rate: float = 0.00015

    # 거래세 (매도 시에만), 2026-01-01 시행 기준
    # 코스피: 0.20% = 증권거래세 0.05% + 농어촌특별세 0.15%
    # 코스닥: 0.20% = 증권거래세 0.20%
    tax_rate_kospi: float = 0.0020
    tax_rate_kosdaq: float = 0.0020

    # 슬리피지 (예상 체결가 - 실제 체결가) 추정치
    slippage_rate: float = 0.0010  # 0.1%


COST = CostConfig()

# =============================================================================
# 백테스트
# =============================================================================
@dataclass(frozen=True)
class BacktestConfig:
    start_date: str = "2020-01-01"
    end_date: str = "2025-12-31"
    benchmark_ticker: str = "069500"  # KODEX 200 ETF (벤치마크)


BACKTEST = BacktestConfig()

# =============================================================================
# 로깅
# =============================================================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = LOG_DIR / "quntbot.log"


# =============================================================================
# 검증 (import 시 자동 실행)
# =============================================================================
def validate() -> list[str]:
    """설정 일관성 체크. 문제가 있으면 경고 메시지 리스트 반환."""
    warnings = []
    if TRADE_MODE == "LIVE" and not KIS.app_key:
        warnings.append("LIVE 모드인데 KIS_APP_KEY 가 비어있습니다.")
    if not DART.enabled:
        warnings.append("DART_API_KEY is empty; quality factors will stay unavailable.")
    if DART.requests_per_minute <= 0 or DART.daily_quota <= 0:
        warnings.append("DART request limit must be greater than 0. Check .env.")
    if KIS.request_timeout_sec <= 0:
        warnings.append("KIS request timeout must be greater than 0. Check .env.")
    if PORTFOLIO.n_holdings <= 0:
        warnings.append("PORTFOLIO.n_holdings 는 1 이상이어야 합니다.")
    if not 0 < PORTFOLIO.min_position_weight <= PORTFOLIO.max_position_weight <= 1:
        warnings.append("PORTFOLIO position weights must satisfy 0 < min <= max <= 1.")
    if EXIT_RULES.stop_loss_pct >= 0:
        warnings.append("EXIT_RULES.stop_loss_pct 는 음수여야 합니다.")
    if EXIT_RULES.trailing_stop_pct >= 0:
        warnings.append("EXIT_RULES.trailing_stop_pct 는 음수여야 합니다.")
    if EXIT_RULES.profit_take_pct <= 0:
        warnings.append("EXIT_RULES.profit_take_pct must be positive.")
    if not 0 < EXIT_RULES.profit_take_sell_fraction < 1:
        warnings.append("EXIT_RULES.profit_take_sell_fraction must be between 0 and 1.")
    if REBALANCE.sell_rank_buffer < PORTFOLIO.n_holdings:
        warnings.append("REBALANCE.sell_rank_buffer must be >= PORTFOLIO.n_holdings.")
    if REBALANCE.min_holding_trading_days < 0:
        warnings.append("REBALANCE.min_holding_trading_days must be zero or greater.")
    return warnings


if __name__ == "__main__":
    # python config.py 로 직접 실행 시 현재 설정 출력 + 검증
    import json

    snapshot = {
        "TRADE_MODE": TRADE_MODE,
        "DATABASE_URL": DATABASE_URL,
        "UNIVERSE": UNIVERSE.__dict__,
        "DART": DART.__dict__,
        "FACTOR": FACTOR.__dict__,
        "PORTFOLIO": {**PORTFOLIO.__dict__, "per_position_cash": PORTFOLIO.per_position_cash},
        "EXIT_RULES": EXIT_RULES.__dict__,
        "REBALANCE": REBALANCE.__dict__,
        "SAFETY": SAFETY.__dict__,
        "COST": COST.__dict__,
        "BACKTEST": BACKTEST.__dict__,
        "TELEGRAM_ENABLED": TELEGRAM.enabled,
        "TELEGRAM_SIGNAL_ENABLED": TELEGRAM_SIGNAL.enabled,
    }
    print(json.dumps(snapshot, indent=2, ensure_ascii=False, default=str))

    issues = validate()
    if issues:
        print("\n[경고]")
        for w in issues:
            print(f"  - {w}")
    else:
        print("\n[OK] 설정 일관성 통과")
