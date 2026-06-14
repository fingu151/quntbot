# Quntbot: 데이터 기반 한국 주식 퀀트 트레이딩 봇 기획안

## Notion 페이지 설정

| 속성 | 값 |
| --- | --- |
| Title | Quntbot: 데이터 기반 한국 주식 퀀트 트레이딩 봇 기획안 |
| Type | Concept |
| Category | Product / Engineering |
| Tags | quant, trading-bot, KIS, Python, risk-management, backtest |
| Status | Draft |
| Audience | 외부 공유용 |
| Last Reviewed | 2026-06-14 |

## 1. 개요

Quntbot은 한국 주식 시장의 KOSPI/KOSDAQ 후보군을 대상으로 가격,
재무, 수급, 리서치, 기술적 지표, 매크로 데이터를 통합해 종목을
점수화하고, 백테스트와 PAPER 안전 검증을 거쳐 리밸런싱 계획을
생성하는 퀀트 트레이딩 봇이다.

핵심 목적은 감정적 판단과 수작업 반복을 줄이고, 데이터 수집부터
전략 검증, 주문 전 안전 확인, 운영 리포트까지 하나의 재현 가능한
투자 운영 시스템으로 묶는 것이다.

## 2. 문제의식

- 개인 또는 소규모 운용 환경에서는 데이터 수집, 종목 선별,
  리밸런싱, 리스크 점검이 분리되어 판단 일관성이 낮다.
- 단일 뉴스나 단일 지표에 의존하면 추격매수, 과최적화, 시장 국면
  오판 위험이 커진다.
- 자동 주문 시스템은 편리하지만, 가격 조회 실패나 오래된 리포트
  같은 작은 오류도 실제 손실로 이어질 수 있다.
- 따라서 자동 실행보다 먼저 근거 수집, 검증, PAPER 우선,
  readiness gate가 설계의 중심이 되어야 한다.

## 3. 대상

- 한국 주식 기반 정량 전략을 실험하고 싶은 개인 투자자 또는 개발자
- 반복 가능한 리밸런싱 프로세스를 만들고 싶은 운영자
- 최종 투자 판단은 사람이 하되, 데이터 준비와 후보 선별을
  자동화하려는 사용자

## 4. 해결 방향

Quntbot은 다음 흐름으로 설계한다.

```text
데이터
  -> 점수화
  -> 백테스트
  -> 리밸런싱 계획
  -> 안전 게이트
  -> PAPER 실행/모니터링
```

- **데이터 계층**: SQLite에 종목, 일봉, 재무, DART 품질 지표,
  투자자 수급, 리서치 리포트, 시장지수, 매크로 지표를 저장한다.
- **팩터 엔진**: 100점 체계로 가치 25, 품질 25, 모멘텀 20,
  배당 5, 기술 15, 보조 신호 10점을 반영한다.
- **전략 계층**: 주간 리밸런싱, 30종목 목표, score-weighted 배분,
  sell rank buffer 40을 기본 구조로 둔다.
- **리스크 관리**: -7% 손절, ATR(14) x 2.2, +16% 부분익절 45%,
  -8% 후행 스탑, 매크로/시장 리스크 오버레이를 사용한다.
- **주문 안전성**: LIVE보다 PAPER를 기본으로 두고, dry-run 리포트,
  날짜 일치, 가격 조회 실패, fallback 가격, 일일 매수/매도 한도,
  readiness check를 모두 통과해야 실행 가능하게 한다.
- **운영 가시성**: 공개 포트폴리오 스냅샷과 에이전트 운영
  대시보드로 현재 보유, 성과, 리스크, 다음 안전 명령을 확인한다.

## 5. 시스템 구조

```text
외부 데이터
  -> SQLite 데이터베이스
  -> 팩터/리서치/매크로 점수화
  -> 백테스트 및 전략 검증
  -> dry-run 리밸런싱 리포트
  -> readiness / preflight 안전 게이트
  -> PAPER 실행 및 장중 스탑 모니터링
  -> 대시보드, 로그, 후속 리뷰
```

### 주요 구성요소

| 영역 | 역할 | 대표 근거 |
| --- | --- | --- |
| 데이터 저장 | 종목, 가격, 재무, 수급, 리서치, 매크로 데이터를 SQLite에 축적 | `src/data/models.py` |
| 팩터 엔진 | 가치, 품질, 모멘텀, 배당, 기술, 보조 신호를 100점으로 결합 | `src/factors/engine.py` |
| 백테스트 | 전략 수익률, MDD, Sharpe, 거래 사유를 검증 | `src/backtest/engine.py` |
| 트레이딩 안전 | dry-run, preflight, 가격 조회, stale report, 일일 주문 한도 확인 | `src/trading/rebalancer.py` |
| 스케줄러 | 장전 데이터 동기화, 리밸런싱, 장중 스탑, 리서치/시그널 수집 | `src/trading/scheduler.py` |
| 운영 리포트 | 공개 포트폴리오 스냅샷과 에이전트 운영 대시보드 생성 | `scripts/generate_public_portfolio_snapshot.py` |

## 6. 현재 검증 근거

- 로컬 DB 기준: `daily_prices` 931,080건, `fundamentals` 1,092,953건,
  `investor_flows` 831,155건, `research_report_signals` 2,496건.
- 최신 공개 포트폴리오 스냅샷 기준: 2026-06-14 20:57 KST, 30종목,
  총자산 약 95,391,138원, 평가손익률 6.29%.
- 최신 dry-run 기준: 2026-06-12, 매도 2건, 매수 5건, 가격 조회 실패
  0건, fallback 가격 0건.
- 최근 전략 검증 리포트 기준: recent 구간의 우수 후보는 수익률
  71.96%, MDD -7.31%, Sharpe 2.3649를 기록했지만, bear 구간은
  -9.57% 수익률과 -14.23% MDD로 나타나 시장 국면별 한계도 명확히
  기록한다.
- 테스트 기록: `progress.md`에는 전체 테스트 `649 passed` 이력이
  남아 있다.

## 7. 기대효과

- 투자 후보 선정 기준을 감각이 아니라 반복 가능한 점수 체계로
  전환한다.
- 주문 전 리스크를 dry-run과 readiness gate에서 먼저 걸러 실제 실행
  오류 가능성을 낮춘다.
- 백테스트, 운영 리포트, 포트폴리오 스냅샷을 통해 전략 변경의 근거를
  축적한다.
- 향후 ETF, 매크로, 리서치, 수급 신호를 독립 모듈로 확장할 수 있다.

## 8. 한계와 원칙

- 이 시스템은 투자 자문이나 수익 보장을 목적으로 하지 않는다.
- 모든 전략 변경은 DB, 로그, 리포트 숫자를 근거로 검토한다.
- 인버스 ETF 헤지는 기능은 있으나 기본 트리거의 성과가 불리하게
  검증되어, 튜닝 전에는 보수적으로 비활성 또는 제한 운용한다.
- LIVE 실행은 별도 승인과 안전 검토 없이는 범위 밖으로 둔다.
- 공개 문서에는 계좌번호, 토큰, 세션 파일, 원문 자격 증명, 민감한
  주문 세부 정보를 포함하지 않는다.

## 9. Notion 운영 제안

- 이 페이지는 Notion의 일반 Documentation DB 또는 Team Wiki DB에
  `Concept` 문서로 등록한다.
- 외부 공유용 링크를 열기 전에는 `현재 검증 근거`의 날짜와 숫자를
  최신 DB/리포트에서 다시 확인한다.
- 전략 수치가 바뀌면 본문을 조용히 덮어쓰기보다 `변경 이력` 섹션을
  추가해 어떤 근거가 갱신됐는지 남긴다.
- LIVE 실행, 인버스 ETF 활성화, 주문 한도 변경처럼 운용 위험이
  커지는 결정은 별도 Decision 문서로 분리한다.

## 10. 근거 파일

- [progress.md](../progress.md)
- [config.py](../config.py)
- [src/data/models.py](../src/data/models.py)
- [src/factors/engine.py](../src/factors/engine.py)
- [src/trading/scheduler.py](../src/trading/scheduler.py)
- [src/trading/rebalancer.py](../src/trading/rebalancer.py)
- [data/public_portfolio_snapshot.json](../data/public_portfolio_snapshot.json)
- [data/dry_run_rebalance_latest.json](../data/dry_run_rebalance_latest.json)

## 11. 변경 이력

| 날짜 | 변경 내용 | 근거 |
| --- | --- | --- |
| 2026-06-14 | 외부 공유용 Notion-ready 기획안 초안 작성 | 로컬 DB, 최신 dry-run, public snapshot, progress log read-back |
