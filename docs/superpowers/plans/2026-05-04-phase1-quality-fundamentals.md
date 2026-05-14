# Phase 1 Quality Fundamentals (DART) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 코스피·코스닥 유동성 기준 유니버스 종목의 ROE / 영업이익률 / 부채비율을 OpenDART에서 분기 단위로 수집해 SQLite에 저장. Phase 2 팩터 엔진의 `quality_score=0.0` 자리를 채우기 위한 데이터 소스 확보.

**Prerequisite:** `docs/superpowers/plans/2026-05-03-environment-recovery.md` 의 모든 Task 가 완료되어 `.venv` 에서 `pytest` 가 정상 동작해야 함. (기존 `venv_broken_py314` 만 있는 상태에서는 `pip install dart-fss` 부터 막힘.)

**Plan dependencies:**
- Must run after: `docs/superpowers/plans/2026-05-03-environment-recovery.md`
- Should run before: `docs/superpowers/plans/2026-05-04-phase2-quality-score.md`
- Independent from: `docs/superpowers/plans/2026-05-04-phase3-stops-simulation.md`
- Recommended commit scope: one commit for DART config/dependency, one for DB models/repositories, one for provider/sync script/tests.

**Background:** 기존 Phase 1 spec(`2026-05-03-phase1-data-pipeline-design.md`)은 pykrx 한계로 ROE/영업이익률/부채비율을 의도적으로 제외했고, "추후 DART 같은 재무제표 소스로 추가한다"고 명시했음. 이 plan이 그 후속.

**Architecture:**
- 새 테이블 `quality_metrics` (ticker, fiscal_year, fiscal_quarter, roe, operating_margin, debt_ratio, published_at, updated_at).
- 기존 `Fundamental` (BPS/PER/PBR…) 와 분리 — DART는 분기 단위(YYYY-QN), pykrx는 일자 단위라서 같은 테이블에 섞으면 join이 꼬인다.
- 새 테이블 `quality_sync_runs` — 시세 sync(`SyncRun`)와 분리. 도메인이 다르고 호출 빈도도 달라 한 테이블에 묶으면 의미가 흐려짐. SQLite + Alembic 부재 환경에서 ALTER TABLE 마이그레이션을 피하는 효과도 있음.
- 새 provider `DartFssFundamentalsProvider`는 별도 인터페이스 `QualityMetricsProvider` 구현. Phase 1 콜렉터(`sync_phase1_data`)는 **건드리지 않고** 별도 entry point `sync_phase1_quality`를 둔다.
- **corp_code 매핑**: dart-fss 의 `dart_fss.api.filings.corp_code.get_corp_code()` 는 OS 캐시 폴더에 ZIP 을 받아 `CORPCODE.xml` 파싱 결과를 자동 캐싱한다. 별도 SQLite 보조 테이블은 두지 않고, `DartFssFundamentalsProvider.__init__` 에서 `dart.get_corp_list()` 한 번 호출해 in-memory `dict[stock_code → corp_code]` 보관. 신규상장/상장폐지 반영을 위해 스크립트에 `--refresh-corp-list` 플래그를 두고, 켜지면 dart-fss 캐시 디렉토리를 비운 뒤 다시 받는다.
- **DART 호출 페이싱**: OpenDART 의 분당/일일 호출 한도는 사이트에 게시되지만 변경 가능하므로 **코드에 하드코딩하지 않고 `.env` 로 외부화**(`DART_REQUESTS_PER_MINUTE`, `DART_DAILY_QUOTA`). `_RateLimiter` 헬퍼가 매 호출 직전 sleep으로 분당 한도를 강제하고, 일일 카운터를 `quality_sync_runs.metric_count` 와 별도로 트래킹. 일일 한도 도달 시 `QualitySyncRun.status="quota_exhausted"` 로 부드럽게 종료.
- 테스트는 `FakeQualityMetricsProvider`로 진행, 네트워크 의존 없음.

**라이브러리 선택 — dart-fss (vs OpenDartReader):**
- OpenDartReader 는 12개월 이상 PyPI 신규 버전 없음(Snyk advisor: "Inactive"). 신규 채택은 위험.
- dart-fss 는 활성 메인테넌스("Sustainable"), Python 3.9~3.13 공식 지원, `dart_fss.fs.extract()` 같은 본격 재무제표 추출 API 제공.
- 단점: 의존성이 무거움(arelle-release, beautifulsoup4, lxml). 서버 환경이 가벼워야 한다면 추후 직접 REST 래퍼로 교체 검토.
- 결정: **dart-fss 채택**.

**Tech Stack:** Python 3.12, dart-fss, SQLAlchemy, pandas, pytest, SQLite.

**Decisions to record (CLAUDE.md "데이터 기반 결정"):**
- ROE 정의: `TTM 당기순이익 / 평균자본총계`. TTM은 `as_of_date` 기준 사용 가능한 최근 4개 분기의 당기순이익 합계다. 평균자본총계는 TTM 시작 직전 분기말 자본총계와 최신 분기말 자본총계의 평균을 우선 사용하고, 시작 직전 자본이 없으면 최신 4개 분기 자본총계 평균, 그것도 부족하면 최신 분기 자본총계를 사용한다.
- 영업이익률: `TTM 영업이익 / TTM 매출액`. 단일 분기 영업이익률은 계절성이 커서 1차 quality 점수에는 쓰지 않는다.
- 부채비율: `최신 분기 부채총계 / 최신 분기 자본총계` (전통적 한국 정의, 100% 미만이 우량). 부채비율은 누적 손익이 아니라 재무상태표 스냅샷이므로 TTM 환산하지 않는다.
- 분기 단위 적용 정책: Phase 2 에서 `as_of_date` 이전 가장 최근 분기 데이터를 사용. DART 보고서 접수일 기준(`published_at <= as_of_date`).
- DART 호출 한도: 코드에 박지 않고 `.env` 로 외부화. 사용자가 OpenDART terms 페이지(https://opendart.fss.or.kr/intro/terms.do) 또는 본인 계정 마이페이지에서 실제 한도를 확인 후 입력. 기본값은 보수적으로 분당 60회 / 일일 10,000회 (실제 한도가 더 크면 사용자가 상향).

---

### Task 1: 환경 및 의존성 준비

**Files:**
- Edit: `requirements.txt`
- Edit: `.env.example`
- Edit: `config.py`
- Read: `README.md`

- [ ] **Step 1: OpenDART API 키 + 호출 한도 환경변수 안내 추가**

`.env.example` 에 다음 라인 추가:
```
# --- OpenDART (Phase 1 quality metrics) ---
# https://opendart.fss.or.kr 회원가입 후 인증키 신청 → 24시간 내 메일로 발급
DART_API_KEY=여기에_DART_API_KEY_입력

# OpenDART terms 페이지(https://opendart.fss.or.kr/intro/terms.do) 또는
# 본인 계정 마이페이지에서 한도 확인 후 채우기. 기본값은 보수적으로 분당 60회 / 일일 10,000회.
DART_REQUESTS_PER_MINUTE=60
DART_DAILY_QUOTA=10000
```

Expected: 사용자가 README의 안내대로 발급 후 .env에 채울 수 있음. 한도를 안 채우면 보수적 기본값으로 동작.

- [ ] **Step 2: 의존성 추가**

`requirements.txt`에 다음 한 줄 추가 (기존 finance-datareader 다음 라인이 자연스러움):
```
dart-fss==0.4.3
```
버전 핀은 PyPI 최신 안정판 확인 후 결정. 추가 후 `.\.venv\Scripts\python.exe -m pip install dart-fss` 실행.

Expected: `import dart_fss` 가능. 무거운 의존성(arelle, lxml 등)이 함께 설치됨을 확인.

- [ ] **Step 3: config.py에 DART 설정 추가**

```python
@dataclass(frozen=True)
class DartConfig:
    api_key: str = os.getenv("DART_API_KEY", "")
    requests_per_minute: int = int(os.getenv("DART_REQUESTS_PER_MINUTE", "60"))
    daily_quota: int = int(os.getenv("DART_DAILY_QUOTA", "10000"))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


DART = DartConfig()
```
그리고 `validate()` 함수에 다음 두 경고 추가:
- `if not DART.enabled: warnings.append("DART_API_KEY 가 비어있어 quality 팩터가 NaN/0 으로 동작합니다.")`
- `if DART.requests_per_minute <= 0 or DART.daily_quota <= 0: warnings.append("DART 호출 한도가 0 이하입니다. .env 확인 필요.")`

Expected: `python config.py` 실행 시 키가 없으면 경고 표시(종료 X). 한도 값도 JSON snapshot 에 노출.

---

### Task 2: quality_metrics 테이블과 repository

**Files:**
- Edit: `src/data/models.py`
- Edit: `src/data/repositories.py`
- Create: `tests/data/test_quality_repository.py`

- [ ] **Step 1: 실패 테스트 작성**

`upsert_quality_metrics` 가 (ticker, fiscal_year, fiscal_quarter) 충돌 시 update만 일어나는지, 신규 행은 insert 되는지 검증.

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/data/test_quality_repository.py -q -p no:cacheprovider`

Expected: FAIL — `QualityMetric` 모델/함수 없음.

- [ ] **Step 3: 모델 정의**

`src/data/models.py` 에 다음 추가:
```python
class QualityMetric(Base):
    __tablename__ = "quality_metrics"
    __table_args__ = (
        UniqueConstraint("ticker", "fiscal_year", "fiscal_quarter",
                         name="uq_quality_metrics_ticker_period"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_quarter: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..4
    roe: Mapped[float | None] = mapped_column(Float)
    operating_margin: Mapped[float | None] = mapped_column(Float)
    debt_ratio: Mapped[float | None] = mapped_column(Float)
    published_at: Mapped[date | None] = mapped_column(Date)  # DART 보고서 접수일
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
```

`src/data/repositories.py` 에 `upsert_quality_metrics` 추가 (기존 `_upsert_many` 패턴 그대로 사용).

- [ ] **Step 4: 테스트 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/data/test_quality_repository.py -q -p no:cacheprovider`

Expected: PASS.

---

### Task 3: QualitySyncRun 테이블과 품질 sync 실행 기록

Task 2는 quality metric 값 자체를 저장하는 테이블/repository 범위이고, Task 3은 sync 작업의 실행 이력만 다룬다. 두 테이블 모두 `src/data/models.py`를 수정하지만 책임이 다르므로 테스트와 구현 단위를 분리한다.

**Files:**
- Edit: `src/data/models.py`
- Create: `tests/data/test_quality_sync_run_model.py` (선택, 단순 추가면 Task 4 통합 테스트로 흡수 가능)

- [ ] **Step 1: 모델 추가**

```python
class QualitySyncRun(Base):
    __tablename__ = "quality_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    year_from: Mapped[int | None] = mapped_column(Integer)
    year_to: Mapped[int | None] = mapped_column(Integer)
    metric_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
```

기존 `SyncRun` 은 그대로 두고, 새 테이블만 추가. `Base.metadata.create_all` 가 새 테이블만 생성하므로 기존 DB도 안전.

- [ ] **Step 2: 검증**

Run: `.\.venv\Scripts\python.exe -m pytest tests/data -q -p no:cacheprovider`

Expected: PASS (기존 데이터 테스트들이 새 모델 import 영향 없이 통과).

---

### Task 4: dart-fss 콜렉터 + RateLimiter + fake provider 테스트

**Files:**
- Create: `src/data/rate_limiter.py`
- Create: `src/data/quality_provider.py`
- Create: `src/data/quality_collector.py`
- Create: `tests/data/test_quality_collector.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/data/test_quality_collector.py` 에 다음 3개 시나리오:
1. `test_sync_phase1_quality_success`: `FakeQualityMetricsProvider` 가 두 종목 × 두 분기 데이터를 반환 → `sync_phase1_quality` 가 4행 저장 + `QualitySyncRun(status="success")` 1건 + `metric_count==4`.
2. `test_sync_phase1_quality_records_failed_run`: provider 가 `RuntimeError("dart down")` 를 던지면 `status="failed"` + `error_message=="dart down"` 기록.
3. `test_sync_phase1_quality_records_quota_exhausted`: provider 가 두 번째 종목에서 `QuotaExhausted` 를 던지면, 첫 번째 종목 데이터는 그대로 저장되고 `QualitySyncRun(status="quota_exhausted")` 가 기록되며 함수가 예외 없이 부드럽게 종료. (이 동작은 위 Step 3 의 sync 흐름 명세와 일치.)

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/data/test_quality_collector.py -q -p no:cacheprovider`

Expected: FAIL.

- [ ] **Step 3: 인터페이스/구현 추가**

```python
class QualityMetricsProvider(Protocol):
    def get_quality_metrics(
        self, ticker: str, *, year_from: int, year_to: int
    ) -> list[dict[str, Any]]: ...
```

`DartFssFundamentalsProvider` 의 책임:
1. `__init__(api_key, rate_limiter, refresh_corp_list=False)` 에서:
   - `dart_fss.set_api_key(api_key)` 1회 호출.
   - `refresh_corp_list=True` 면 dart-fss 캐시 디렉토리(`dart_fss.utils.cache.cache_dir()`)의 `CORPCODE.zip` / `CORPCODE.xml` 삭제.
   - `dart.get_corp_list()` 호출 → 결과를 `self._stock_to_corp: dict[str, str]` 로 변환 (stock_code 가 비어있는 비상장 종목은 제외). dart-fss 가 ZIP/xml 캐싱을 자동 처리하므로 별도 SQLite 캐시 불필요.
2. `get_quality_metrics(ticker, year_from, year_to)`:
   - `corp_code = self._stock_to_corp[ticker]` (KeyError 면 빈 리스트 반환 + 로그).
   - `self._rate_limiter.acquire()` 로 페이싱 강제.
   - `dart_fss.fs.extract(corp_code, bgn_de=f"{year_from}0101")` 결과(bs/is dict)에서 매출액·영업이익·당기순이익·자본총계·부채총계를 분기별로 추출 → ROE/영업이익률/부채비율 계산.

`_RateLimiter` (`src/data/rate_limiter.py` 신규):
```python
import time
from collections import deque
from threading import Lock

class RateLimiter:
    def __init__(self, *, requests_per_minute: int, daily_quota: int):
        self.requests_per_minute = requests_per_minute
        self.daily_quota = daily_quota
        self._minute_window: deque[float] = deque()
        self._daily_count = 0
        self._daily_started_at = time.time()
        self._lock = Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.time()
            # 일일 카운터 리셋 (24h)
            if now - self._daily_started_at >= 86400:
                self._daily_count = 0
                self._daily_started_at = now
            if self._daily_count >= self.daily_quota:
                raise QuotaExhausted("DART daily quota reached")
            # 분당 한도 sleep
            while self._minute_window and now - self._minute_window[0] >= 60:
                self._minute_window.popleft()
            if len(self._minute_window) >= self.requests_per_minute:
                sleep_for = 60 - (now - self._minute_window[0])
                time.sleep(max(sleep_for, 0))
                now = time.time()
            self._minute_window.append(now)
            self._daily_count += 1
```

`sync_phase1_quality(engine, provider, year_from, year_to, tickers=None)`:
- tickers None 이면 `Stock` 활성 목록 전체, 아니면 지정 종목만 순회.
- `QuotaExhausted` 잡으면 `QualitySyncRun.status="quota_exhausted"` + 그때까지 저장한 행 유지 + 부드러운 종료.
- 그 외 예외는 `QualitySyncRun.status="failed"` + error_message.
- 정상 종료 시 `status="success"` + `metric_count`.

- [ ] **Step 4: 테스트 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/data/test_quality_collector.py -q -p no:cacheprovider`

Expected: PASS.

- [ ] **Step 5: RateLimiter 단위 테스트**

`tests/data/test_rate_limiter.py` 신규. `time.time` 과 `time.sleep` 을 monkeypatch 로 가짜화해 실시간 의존 없이 검증:
1. `test_rate_limiter_allows_under_limit`: requests_per_minute=3 으로 초기화 후 3번 acquire → sleep 호출 0회.
2. `test_rate_limiter_sleeps_when_minute_window_full`: requests_per_minute=2 로 초기화 후 같은 가짜 시각에 acquire 3번 → 세 번째 호출에서 `time.sleep` 가 호출됨 (인자가 양수).
3. `test_rate_limiter_raises_quota_exhausted_after_daily_limit`: daily_quota=2 로 초기화 후 acquire 3번 → 세 번째에서 `QuotaExhausted` raise.
4. `test_rate_limiter_resets_daily_counter_after_24h`: daily_quota=1, 첫 acquire 후 가짜 시각을 `+86401` 초로 점프 → 두 번째 acquire 가 예외 없이 통과.

Run: `.\.venv\Scripts\python.exe -m pytest tests/data/test_rate_limiter.py -q -p no:cacheprovider`

Expected: PASS. 실제 sleep 으로 인한 테스트 지연 없음(monkeypatch 덕분).

---

### Task 5: 수동 실행 스크립트

**Files:**
- Create: `scripts/sync_phase1_quality.py`
- Create: `tests/data/test_quality_sync_script.py`

- [ ] **Step 1: 실패 테스트 작성**

argparse 인자(`--year-from`, `--year-to` 기본값=현재 회계연도와 직전 연도, `--tickers`) 검증, 주입한 sync 함수가 호출되는지 확인.

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/data/test_quality_sync_script.py -q -p no:cacheprovider`

Expected: FAIL.

- [ ] **Step 3: 스크립트 구현**

`scripts/sync_phase1_quality.py` 의 `parse_args / run / main` 구현.

argparse 인자:
- `--year-from` / `--year-to` (기본값: 직전 회계연도, 현재 회계연도)
- `--tickers` (옵션, 공백 구분 종목코드 리스트. 미지정 시 활성 종목 전체)
- `--refresh-corp-list` (옵션 boolean. dart-fss CORPCODE 캐시 강제 무효화 후 재다운)

`DartFssFundamentalsProvider` 인스턴스화 시:
- `DART.api_key` 가 비어있으면 친절한 에러 메시지로 종료.
- `RateLimiter(requests_per_minute=DART.requests_per_minute, daily_quota=DART.daily_quota)` 생성 후 provider 에 주입.
- `--refresh-corp-list` 가 켜져 있으면 provider `__init__(refresh_corp_list=True)` 호출.

- [ ] **Step 4: 테스트 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/data/test_quality_sync_script.py -q -p no:cacheprovider`

Expected: PASS.

---

### Task 6: 전체 검증

**Files:**
- Read: 이 plan에서 만들거나 수정한 모든 파일.

- [ ] **Step 1: 전체 데이터 테스트 실행**

Run: `.\.venv\Scripts\python.exe -m pytest tests/data -q -p no:cacheprovider`

Expected: PASS.

- [ ] **Step 2: AST 신택스 체크**

Run: `.\.venv\Scripts\python.exe -m py_compile config.py src/data/models.py src/data/repositories.py src/data/rate_limiter.py src/data/quality_provider.py src/data/quality_collector.py scripts/sync_phase1_quality.py`

Expected: 종료 코드 0.

- [ ] **Step 3: 옵션 — 실 API 1종목 sync 검증**

DART API 키가 설정된 환경에서 1종목(예: 005930 삼성전자)만 작은 기간으로 직접 sync. DB row 1건 이상 확인.

Run: `.\.venv\Scripts\python.exe scripts/sync_phase1_quality.py --tickers 005930 --year-from 2024 --year-to 2025`

Expected: `quality_metrics` 테이블에 행 추가, ROE 등이 합리적 범위 (-50% ~ 50%). `quality_sync_runs` 에 success 행 1건.
