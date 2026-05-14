# Buy Filter Policy Design

## Goal

quntbot의 신규 매수 후보에서 자동매매에 부적합한 종목을 사전에 제외한다.

팩터 엔진은 점수로 "좋아 보이는 종목"을 고르고, buy filter는 "사면 안 되는 종목"을 제거한다. 이 문서는 다른 AI 에이전트가 같은 기준으로 Phase 2/3/4 구현을 이어갈 수 있도록 확정된 매수 필터 정책을 기록한다.

## Scope

이 문서는 정책 설계 문서다. 아직 코드 구현은 하지 않는다.

적용 대상:

- 신규 매수 후보 선정
- 백테스트의 리밸런싱 매수
- 향후 KIS PAPER/LIVE 주문 전 최종 안전 필터

비적용 대상:

- 이미 보유 중인 종목의 강제 매도 조건
- 손절/트레일링 스톱
- 텔레그램 알림 상세 문구
- dashboard 표시 방식

## Timing Policy

Look-ahead bias를 피하기 위해 다음 원칙을 사용한다.

- `execution_date`: 실제 매수/매도 체결을 가정하는 날짜.
- `signal_date`: `execution_date`의 직전 거래일.
- 신호 계산에는 `signal_date`까지 확정된 데이터만 사용한다.
- 리밸런싱 매수/매도 체결가는 `execution_date` 시가를 사용한다.
- 당일 평가/equity curve는 `execution_date` 종가를 사용한다.
- 재무제표 quality 데이터는 `published_at <= signal_date`인 행만 사용한다.
- `published_at`이 없는 재무제표 데이터는 사용하지 않는다.

## Filter Decisions

### 1. Liquidity Filter

신규 매수 후보는 최근 20거래일 평균 거래대금이 20억 원 이상이어야 한다.

정책:

```text
avg_trading_value_20d >= 2_000_000_000
```

근거:

- 10억 원은 후보군을 넓게 유지하지만 체결/슬리피지 리스크가 커질 수 있다.
- 50억 원은 더 보수적이지만 후보가 과하게 좁아질 수 있다.
- 20억 원은 MVP 기준 균형형으로 사용자 선택 완료.

### 2. Price Filter

1주 가격이 1,000원 미만인 종목은 신규 매수 후보에서 제외한다.

정책:

```text
execution_open >= 1_000
```

`execution_open`은 B안 백테스트/운영 체결 정책에 맞춘 `execution_date` 시가다.

### 3. Risk Status Filter

다음 상태에 해당하는 종목은 신규 매수 후보에서 제외한다.

- 거래정지
- 관리종목
- 투자주의
- 투자경고
- 투자위험
- 기타 KRX 공식 데이터에서 자동매매 부적합 상태로 식별되는 종목

데이터 소스:

- KRX 공식 데이터를 우선 사용한다.
- pykrx로 안정적으로 가져올 수 있으면 pykrx를 사용한다.
- 부족하면 KRX 공식 CSV/API 수집기를 Phase 1 보강 task로 만든다.

상태 정보 미확인 정책:

```text
risk_status_unknown -> exclude from new buys
```

사용자 결정:

- 상태 정보가 확인되지 않는 종목은 보수적으로 신규 매수 제외한다.

### 4. Valuation Data Quality Filter

PER/PBR이 0 이하인 종목은 신규 매수 후보에서 제외한다.

정책:

```text
per > 0
pbr > 0
```

근거:

- PER <= 0은 적자 기업이거나 데이터가 비정상/계산 불가일 가능성이 크다.
- PBR <= 0도 정상 투자 지표로 보기 어렵다.
- 사용자는 0 이하 제외를 선택했다.

### 5. Severe Loss Filter

최근 2개 분기 연속 심한 적자 기업은 신규 매수 후보에서 제외한다.

정책:

```text
exclude if operating_margin < -0.10 for each of the latest 2 quarters
or
exclude if net_margin < -0.10 for each of the latest 2 quarters
```

정의:

- `operating_margin = operating_income / revenue`
- `net_margin = net_income / revenue`
- 최근 2개 분기는 `published_at <= signal_date`인 quality 재무제표 중 가장 최근 2개 분기를 의미한다.
- `published_at`이 없는 재무제표 데이터는 사용하지 않는다.

근거:

- 단순 적자 여부만으로 제외하면 일시적 비용 때문에 후보가 과하게 줄 수 있다.
- 매출 대비 -10% 이하의 적자가 2분기 연속이면 본업/최종손익 악화가 의미 있다고 본다.
- 사용자는 균형형 기준을 선택했다.

### 6. Quality Coverage Filter

사용자는 quality 데이터가 없는 종목 처리에 대해 C안을 선택했다.

개별 종목 quality 검증 조건:

```text
available_count(roe, operating_margin, debt_ratio) >= 2
```

후보군 quality 커버리지 조건:

```text
quality_verified_candidates / final_candidate_pool >= 0.70
```

quality 필터 활성화 조건:

- 최종 후보군의 quality 검증 종목 비율이 70% 이상이면 quality 필터를 활성화한다.
- 70% 미만이면 quality 필터는 신규 매수 제외 조건으로 쓰지 않고 warning 로그만 남긴다.

활성화 시 신규 매수 조건:

```text
roe > 0
debt_ratio < 3.00
```

비활성화 시:

```text
quality coverage < 70%
-> do not exclude by ROE/debt_ratio
-> log warning: quality_coverage_low
-> continue with value/momentum-driven candidate selection
```

주의:

- 이 정책은 DART 데이터가 부족한 초기 단계에서 후보군이 0개가 되는 것을 막기 위한 균형안이다.
- DART 수집이 안정화되면 quality 필터를 더 엄격하게 바꾸는 후속 plan을 만들 수 있다.

### 7. Gap / Extreme Move Filter

당일 신규 매수는 오늘 시가가 전일 종가 대비 ±20% 이상 움직인 종목을 제외한다.

정책:

```text
abs(execution_open / previous_close - 1.0) < 0.20
```

제외 예:

- 전일 종가 10,000원, 오늘 시가 12,000원: +20%, 제외
- 전일 종가 10,000원, 오늘 시가 8,000원: -20%, 제외
- 전일 종가 10,000원, 오늘 시가 11,900원: +19%, 통과
- 전일 종가 10,000원, 오늘 시가 8,100원: -19%, 통과

근거:

- B안 백테스트는 `execution_date` 시가 체결을 가정한다.
- 따라서 전일 종가 대비 오늘 시가를 보는 것이 실제 체결 리스크와 가장 가깝다.
- 급등 추격매수와 급락 낙폭과대 함정을 모두 피한다.

### 8. Listing Age Filter

상장 후 365일 미만 종목은 신규 매수 후보에서 제외한다.

정책:

```text
execution_date - listing_date >= 365 days
```

데이터 소스:

- KRX 공식 상장일 데이터를 우선 사용한다.

상장일 미확인 정책:

```text
listing_date_unknown -> allow, but log warning
```

사용자 결정:

- 상장일이 확인되지 않는 종목은 신규 매수 후보에는 남긴다.
- warning 로그에 `listing_date_unknown`을 기록한다.

근거:

- 상장일 미확인을 모두 제외하면 데이터 누락 때문에 정상 종목도 빠질 수 있다.
- KRX 공식 데이터를 우선 사용하면 미확인 케이스는 많지 않을 것으로 기대한다.

## Recommended Filter Order

구현 시 추천 순서는 다음과 같다.

1. Risk status filter
2. Listing age filter
3. Price filter
4. Liquidity filter
5. Valuation data quality filter
6. Severe loss filter
7. Quality coverage/filter activation
8. Gap / extreme move filter

이 순서의 의도:

- 거래 불가능하거나 자동매매 부적합한 종목을 먼저 제거한다.
- 데이터 품질/상장 기간 같은 구조적 문제를 먼저 제거한다.
- 그 다음 유동성/가격/밸류/재무 상태를 적용한다.
- 마지막에 execution_date 시가가 필요한 급등락 필터를 적용한다.

## Logging Requirements

필터는 종목을 제외한 이유를 추적 가능하게 남겨야 한다.

추천 reason code:

```text
risk_status_excluded
risk_status_unknown
listing_too_young
listing_date_unknown
price_below_min
liquidity_below_min
per_non_positive
pbr_non_positive
severe_operating_loss
severe_net_loss
quality_coverage_low
quality_metrics_insufficient
roe_non_positive
debt_ratio_too_high
gap_move_too_large
```

주의:

- `listing_date_unknown`은 경고 후 통과 reason이다.
- `quality_coverage_low`는 quality 필터 비활성화 경고 reason이다.
- `risk_status_unknown`은 제외 reason이다.

## Configuration Candidates

향후 `config.py`에 별도 dataclass를 추가한다면 다음 값들이 후보가 된다.

```python
@dataclass(frozen=True)
class BuyFilterConfig:
    min_avg_trading_value_20d: float = 2_000_000_000
    min_price: float = 1_000
    min_listing_age_days: int = 365
    max_abs_open_gap_pct: float = 0.20
    severe_loss_margin_threshold: float = -0.10
    severe_loss_quarters: int = 2
    min_quality_metric_count: int = 2
    min_quality_coverage_ratio: float = 0.70
    min_roe: float = 0.0
    max_debt_ratio: float = 3.0
    exclude_unknown_risk_status: bool = True
    exclude_unknown_listing_date: bool = False
```

## Implementation Notes For Future Agents

- Do not implement this policy before the user explicitly asks to leave Plan mode.
- Before implementation, add or update a plan file under `docs/superpowers/plans/`.
- Use TDD:
  1. Write failing tests for each filter.
  2. Confirm failure.
  3. Implement the filter.
  4. Run targeted tests.
  5. Run full tests.
- Keep buy filters separate from score calculation where possible.
- A likely module location is `src/factors/filters.py` or `src/trading/buy_filters.py`; choose based on whether the filter is used first in Phase 2 ranking output or Phase 4 order placement.
- Backtest must apply the same buy filter policy as live/paper trading unless explicitly testing a baseline without filters.

## Open Questions

These are not blockers for the current policy, but should be revisited before implementation.

- Exact KRX data source endpoint/file for risk status.
- Exact KRX data source endpoint/file for listing date.
- Whether risk status should be refreshed daily before market open.
- Whether quality coverage should be measured over top-ranked candidates before filters or after basic filters.
- Whether existing holdings that later fail a buy filter should be held until normal rebalance/exit, or sold immediately. Current scope covers only new buys.
