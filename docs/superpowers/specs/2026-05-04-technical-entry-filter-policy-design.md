# Technical Entry Filter Policy Design

## Goal

quntbot의 2차 필터로 기술적 분석 기반 신규 매수 타이밍 필터를 둔다.

1차 buy filter는 위험한 종목, 데이터 품질이 낮은 종목, 자동매매 부적합 종목을 제거한다. 2차 technical entry filter는 남은 후보 중 "지금 신규 진입해도 되는 타이밍인지"를 확인한다.

## Scope

이 문서는 정책 설계 문서다. 아직 코드 구현은 하지 않는다.

적용 대상:

- 신규 매수 후보
- 백테스트 리밸런싱 매수
- 향후 KIS PAPER/LIVE 주문 전 최종 진입 타이밍 확인

비적용 대상:

- 보유 종목 매도 조건
- 손절/트레일링 스톱
- 가치/퀄리티/모멘텀 점수 계산 자체
- 분봉/틱 기반 초단기 진입 신호

## Role In Strategy

기술적 필터는 수익률 예측 모델이 아니다.

정책:

```text
Use technical filters as risk/timing filters, not as alpha prediction.
```

의도:

- 하락 추세가 뚜렷한 종목 회피
- 이미 과열된 종목 추격매수 회피
- 변동성이 과한 종목 회피
- 1차 필터와 팩터 랭킹 사이에서 진입 타이밍을 보수적으로 조정

추천 흐름:

```text
Universe
-> 1차 buy filter
-> 2차 technical entry filter
-> factor ranking
-> portfolio sizing
-> execution
```

팩터 랭킹 후에 기술적 필터를 적용할 수도 있지만, MVP에서는 필터 통과 후보만 랭킹하는 방식이 더 단순하다.

## Timing Policy

Look-ahead bias를 피하기 위해 B안 백테스트 정책을 따른다.

- `execution_date`: 실제 체결을 가정하는 날짜.
- `signal_date`: `execution_date`의 직전 거래일.
- 기술적 지표 계산에는 `signal_date`까지 확정된 가격 데이터만 사용한다.
- 신규 매수 체결가는 `execution_date` 시가를 사용한다.
- 당일 평가는 `execution_date` 종가를 사용한다.

주의:

- `execution_date` 시가는 급등락/gap filter에는 사용할 수 있다.
- 이동평균, RSI, 변동성 같은 기술 지표는 `execution_date` 당일 종가를 사용하면 안 된다.

## MVP Technical Conditions

2차 기술적 필터 MVP는 네 가지 조건을 사용한다.

### 1. Short-Term Trend: Close Above MA20

정책:

```text
signal_close > ma20
```

정의:

- `signal_close`: `signal_date`의 종가.
- `ma20`: `signal_date`까지의 최근 20거래일 종가 단순이동평균.

의도:

- 단기 추세가 완전히 무너진 종목을 신규 매수하지 않는다.

### 2. Medium-Term Trend: MA60 Slope Positive

정책:

```text
ma60_today > ma60_20_trading_days_ago
```

정의:

- `ma60_today`: `signal_date`까지의 최근 60거래일 종가 단순이동평균.
- `ma60_20_trading_days_ago`: `signal_date`에서 20거래일 전 시점의 60일 이동평균.

의도:

- 중기 추세가 꺾인 종목을 피한다.
- 스윙 전략이므로 단기 반등보다 중기 방향성을 더 신뢰한다.

데이터 요구:

- 최소 80거래일 이상의 종가가 필요하다.
- 데이터가 부족하면 이 조건은 미충족으로 처리한다.

### 3. Overheat Filter: RSI(14) Below 75

정책:

```text
rsi14 < 75
```

정의:

- RSI는 `signal_date`까지의 종가로 계산한다.
- 기본 기간은 14거래일.

의도:

- 이미 과열된 종목을 추격매수하지 않는다.

주의:

- RSI가 낮다고 무조건 좋은 것은 아니다.
- 이 필터는 과열 회피 목적이며, 과매도 매수 신호로 쓰지 않는다.

### 4. Volatility Filter: 20-Day Daily Volatility Below 5%

정책:

```text
std(daily_return_20d) < 0.05
```

정의:

- `daily_return_20d`: `signal_date`까지의 최근 20거래일 일간 종가 수익률.
- 표준편차는 decimal 기준이다. 예: 0.05 = 5%.

의도:

- 최근 변동성이 과도한 종목을 피한다.
- 자동매매에서 예상보다 큰 슬리피지와 리스크를 줄인다.

## Pass Rule

기술적 필터는 너무 엄격하게 적용하지 않는다.

정책:

```text
Pass if at least 3 of 4 technical conditions are satisfied.
```

조건 목록:

1. `signal_close > ma20`
2. `ma60_today > ma60_20_trading_days_ago`
3. `rsi14 < 75`
4. `volatility_20d < 0.05`

통과 예:

- 4개 중 4개 만족: 통과
- 4개 중 3개 만족: 통과
- 4개 중 2개 이하 만족: 신규 매수 제외

근거:

- 모든 조건을 강제하면 좋은 가치주가 일시 조정 중일 때 과하게 제외될 수 있다.
- 3개 이상 만족은 추세/과열/변동성을 균형 있게 반영한다.

## Data Requirements

필요 데이터:

- `daily_prices.close`
- 최소 80거래일 이상 종가 히스토리
- `signal_date` 기준 최근 20거래일 수익률

기술 지표 계산에는 다음 데이터를 사용하지 않는다.

- `execution_date` 종가
- 미래 가격
- 아직 published_at이 도달하지 않은 재무제표

## Missing Data Policy

데이터가 부족해 특정 조건을 계산할 수 없으면 해당 조건은 미충족으로 본다.

정책:

```text
indicator_missing -> condition_failed
```

예:

- 80거래일 미만 데이터라 MA60 slope 계산 불가 → MA60 slope 조건 실패
- 20거래일 미만 데이터라 volatility 계산 불가 → volatility 조건 실패
- 14거래일 미만 데이터라 RSI 계산 불가 → RSI 조건 실패

단, missing reason은 로그에 남긴다.

## Logging Requirements

기술적 필터는 종목별 통과/탈락 이유를 추적 가능하게 남겨야 한다.

추천 reason code:

```text
technical_pass
technical_failed
ma20_failed
ma60_slope_failed
rsi_overheated
volatility_too_high
technical_indicator_missing
```

추천 로그 필드:

```text
ticker
signal_date
passed_conditions
failed_conditions
ma20
ma60_today
ma60_20d_ago
rsi14
volatility_20d
```

## Configuration Candidates

향후 `config.py`에 별도 dataclass를 추가한다면 다음 값들이 후보가 된다.

```python
@dataclass(frozen=True)
class TechnicalFilterConfig:
    ma_short_window: int = 20
    ma_medium_window: int = 60
    ma_slope_lookback_days: int = 20
    rsi_window: int = 14
    max_rsi: float = 75.0
    volatility_window: int = 20
    max_daily_volatility: float = 0.05
    min_passed_conditions: int = 3
```

## Interaction With 1st Buy Filter

1차 buy filter와 2차 technical entry filter는 역할이 다르다.

1차 buy filter:

- 거래 위험 상태
- 상장 기간
- 가격
- 유동성
- PER/PBR 데이터 품질
- 심한 적자
- quality 커버리지
- gap/급등락

2차 technical entry filter:

- MA20 위 여부
- MA60 기울기
- RSI 과열 여부
- 최근 변동성

원칙:

```text
Both filters must pass for a new buy.
```

단, quality coverage가 70% 미만이라 1차 quality 필터가 비활성화된 경우에도 technical filter는 그대로 적용한다.

## Implementation Notes For Future Agents

- Do not implement this policy before the user explicitly asks to leave Plan mode.
- Before implementation, add or update a plan file under `docs/superpowers/plans/`.
- Use TDD:
  1. Write tests for MA20, MA60 slope, RSI, volatility, and 3-of-4 pass rule.
  2. Confirm tests fail.
  3. Implement indicator calculations.
  4. Run targeted tests.
  5. Run full tests.
- Keep technical filters deterministic and based only on stored daily prices.
- Do not introduce external TA libraries unless the local implementation becomes complex. These four indicators are simple enough to implement with pandas.
- Backtest and future live/paper trading must use the same technical filter policy.

## Open Questions

These are not blockers for the current MVP policy, but should be revisited after initial backtests.

- Whether MA20 should use close or execution_open for final check.
- Whether RSI threshold should be 70 instead of 75 if too many overheated names pass.
- Whether volatility threshold should differ for KOSPI and KOSDAQ.
- Whether 3-of-4 pass rule should become 4-of-4 in LIVE mode.
- Whether technical filter should run before ranking or after top-K ranking. MVP recommendation is before ranking.
