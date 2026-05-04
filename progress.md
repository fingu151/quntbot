# quntbot Progress Log

이 파일은 quntbot 개발을 이어가면서 현재 완료 단계, 중요한 문제점, 해결 내용, 개선 사안을 계속 기록하기 위한 작업 로그입니다.

## 2026-05-04 09:47 KST

### 현재 완료 단계

- GitHub ZIP 다운로드본 기준 작업 폴더를 `C:\Users\n\Downloads\quntbot-main\quntbot-main`로 확정했다.
- Phase 0 환경 세팅을 이 노트북에서 완료했다.
- Python 3.12.10 기반 새 가상환경 `venv`를 생성했다.
- `requirements.txt` 의존성 설치를 완료했다.
- `.env.example`을 `.env`로 복사했다.
- `python config.py` 설정 검증을 통과했다.
- 전체 테스트를 실행했고 `33 passed`로 통과했다.

### 확인된 문제점

- 기존 설치된 Python은 `3.14.3`이었다.
- `Python 3.14`에서는 `pandas==2.2.3` 설치 시 미리 빌드된 Windows wheel을 사용하지 못하고 소스 빌드로 넘어갔다.
- 그 결과 Visual Studio 빌드 도구의 `vswhere.exe`를 찾지 못해 `pip install -r requirements.txt`가 실패했다.
- 기존 `venv`는 깨진 상태였다. 내부 실행 파일이 현재 프로젝트 경로가 아니라 Codex 샌드박스 임시 경로를 참조해 실행되지 않았다.
- `.env.example`의 placeholder 값이 그대로 `.env`에 들어가면 텔레그램 설정이 실제로 켜진 것처럼 인식되는 문제가 있었다.

### 처리 내용

- 공식 Python 3.12.10 Windows installer를 내려받아 사용자 계정 영역에 설치했다.
- 깨진 기존 `venv`는 삭제하지 않고 `venv_broken_py314`로 보존 이동했다.
- Python 3.12.10으로 새 `venv`를 만들었다.
- 새 가상환경에서 `pip`를 업데이트했다.
- `requirements.txt` 설치를 다시 실행해 성공시켰다.
- `.env`의 `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` placeholder 값을 빈 값으로 정리했다.
- 정리 후 `TELEGRAM_ENABLED`가 `false`로 정상 표시되는 것을 확인했다.

### 검증 결과

```text
python config.py
[OK] 설정 일관성 통과
```

```text
python -m pytest
33 passed
```

### 중요한 운영 메모

- 현재는 `TRADE_MODE=PAPER` 모드다.
- 실제 KIS API 키와 계좌번호는 아직 `.env`에 입력하지 않았다.
- 텔레그램 토큰과 채팅 ID도 아직 입력하지 않았다.
- `.env`는 절대 GitHub에 올리면 안 된다.
- ZIP 다운로드본이라 `.git` 연결은 없을 수 있다. GitHub로 다시 올리는 흐름이 필요해지면 Git 설치와 저장소 연결을 별도로 정리해야 한다.

### 다음 개발 단계

- Phase 1: 데이터 파이프라인 개발을 이어간다.
- 우선순위는 다음 순서가 적절하다.
  1. KOSPI200/KOSDAQ150 유니버스 수집 코드 확인 및 보강
  2. 일봉 시세 수집 코드 확인 및 보강
  3. 재무 데이터 수집 코드 확인 및 보강
  4. SQLite 저장 구조와 repository 계층 검증
  5. 실제 pykrx 데이터로 최소 샘플 수집 테스트

### 개선 사안

- `.env.example`의 placeholder 값 때문에 boolean 설정이 켜진 것처럼 보일 수 있으므로, 추후 템플릿 값을 빈 값 또는 명확한 주석 형태로 바꾸는 것이 좋다.
- Python 버전 호환성을 README에 더 명확히 적는 것이 좋다. 현재 의존성 기준으로는 Python 3.12 사용을 권장한다.
- ZIP 다운로드 작업 방식은 빠르게 이어가기에는 충분하지만, 장기적으로는 Git for Windows 설치 후 clone 기반으로 전환하는 것이 좋다.

## 2026-05-04 Phase 구현 범위 점검

### 현재 코드 기준 구현 판단

- Phase 0: 완료로 판단한다. 환경 설정, 의존성 설치, 설정 검증, 테스트 실행이 모두 성공했다.
- Phase 1: 기본 구현은 존재한다. `src/data`에 pykrx 기반 유니버스/일봉/기초지표 수집기, SQLite 모델, repository, sync 스크립트가 있다. 다만 실제 KRX 데이터를 끝까지 받아 DB에 넣는 실데이터 smoke test는 아직 필요하다.
- Phase 2: 기본 구현은 존재한다. `src/factors`에 PER/PBR 가치 점수와 6개월 모멘텀 점수 계산, 랭킹 스크립트가 있다. 하지만 요구사항의 quality 지표(ROE, 영업이익률, 부채비율)는 아직 구현되지 않았고 `quality_score`가 0.0으로 고정되어 있다.
- Phase 3: 기본 백테스트 엔진은 존재한다. 리밸런싱 기반 매수/매도, 수수료/세금/슬리피지, CAGR/MDD/Sharpe/win rate 계산, 실행 스크립트가 있다. 다만 손절(-8%)과 트레일링 스탑(-10%)은 백테스트에 아직 반영되지 않은 것으로 보인다.
- Phase 4: 아직 미구현으로 판단한다. `src/trading`에는 `__init__.py`만 있고 KIS 주문, 계좌조회, 안전장치, 실시간 모니터링 코드가 없다.
- Phase 5: 아직 미구현으로 판단한다. `src/notify`에는 `__init__.py`만 있고 텔레그램 알림이나 Streamlit 대시보드 구현이 없다.

### 중요한 문제점

- README와 progress 일부 한글이 cp949/utf-8 인코딩 문제로 깨져 보인다. 코드 자체는 컴파일되지만 문서 가독성이 나쁘다.
- `src/data/collectors.py`의 pykrx 컬럼명 문자열도 화면상 깨져 보인다. 컴파일은 통과하지만 실제 수집 결과에서 open/high/low/close/volume 등이 제대로 매핑되는지 반드시 실데이터로 확인해야 한다.
- 현재 테스트는 33개 모두 통과하지만, 실제 pykrx 네트워크 호출과 장기간 데이터 수집 안정성을 충분히 보장하지는 않는다.

### 다음 우선순위 제안

1. Phase 1 실데이터 smoke test: 최근 며칠치 데이터로 DB 저장이 실제로 되는지 확인한다.
2. 깨진 한글 문서와 pykrx 컬럼명 매핑을 정리한다.
3. Phase 2 quality 지표를 요구사항대로 구현한다.
4. Phase 3 백테스트에 손절과 트레일링 스탑을 반영한다.
5. Phase 4 KIS 모의투자 주문 모듈은 위 단계 검증 후 진행한다.

## 2026-05-04 다른 AI 작업 인수인계 반영

### 읽은 인수인계 자료

- `docs/superpowers/2026-05-04-handoff.md`
- `docs/superpowers/plans/2026-05-04-phase1-quality-fundamentals.md`
- `docs/superpowers/plans/2026-05-04-phase2-quality-score.md`
- `docs/superpowers/plans/2026-05-04-phase3-stops-simulation.md`
- `docs/superpowers/plans/2026-05-04-cost-parameters-recheck.md`
- `AGENTS.md`
- `CLAUDE.md`

### 인수인계 핵심 내용

- 신규 4개 plan 이 작성되어 있었다.
  - 거래세/비용 재검토
  - Phase 3 손절/트레일링 백테스트 반영
  - Phase 1 DART quality 재무지표 수집
  - Phase 2 quality_score 실제 계산
- 기존 review 항목 15개 중 #1, #2, #13은 반영 완료로 기록되어 있었다.
- 다음 즉시 할 일은 review #3, 그 다음은 #4로 정리되어 있었다.

### 이번에 처리한 작업

- Review #3 반영:
  - `docs/superpowers/plans/2026-05-04-phase3-stops-simulation.md`의 Task 1 Step 2를 보강했다.
  - `_load_prices` 반환값을 `float`에서 `{"open": ..., "close": ...}`로 바꿀 때 영향을 받는 3곳을 명시했다.
    1. `available_prices` 생성부
    2. `_positions_value(positions, available_prices)` 호출부
    3. `equity_curve` 기록부의 포지션 평가액 계산
- Review #4 반영:
  - `docs/superpowers/plans/2026-05-04-cost-parameters-recheck.md`의 Task 4 Step 1을 보강했다.
  - 비용 변경 전/후 백테스트 비교 전에 `data/quntbot.db`와 시드 데이터 존재 여부를 확인하도록 명시했다.
  - 현재 실제 스크립트 인자인 `--start-date` / `--end-date` 기준으로 sync 예시 명령을 수정했다.
  - 빈 DB에서 실행한 백테스트 결과는 비용 변경 영향 측정값으로 쓰지 않도록 명시했다.

### 확인된 환경 차이

- 인수인계 문서에는 `.venv`가 없고 환경복구가 필요하다고 적혀 있었지만, 실제 현재 환경은 `venv`가 존재하며 Python 3.12.10 기반으로 동작한다.
- `data/quntbot.db`는 아직 존재하지 않는다. 따라서 실데이터 기반 백테스트 비교는 Phase 1 sync 이후 가능하다.

### 검증 결과

```text
pytest -q -p no:cacheprovider
33 passed
```

### 다음 미반영 우선순위

- Review #5: Phase 2 z-score outlier 영향 단정 오류 보강
- Review #6: `combine_scores`의 `fillna(0.0)` 동작과 quality 결측 정책 정리
- Review #7: ROE 분기 데이터 TTM 환산 여부 결정
- Review #8: 손절과 트레일링 동시 트리거 시 우선순위 명시
- Review #9: 손절 후 재진입 금지 옵션 결정
- Review #10~#15: 나머지 문서/작업 단위 보강

## 2026-05-04 Review #5~#6 반영

### 처리한 작업

- Review #5 반영:
  - `docs/superpowers/plans/2026-05-04-phase2-quality-score.md`의 부채비율 outlier 설명을 수정했다.
  - 기존 문장은 "z-score는 정렬에만 쓰이므로 outlier가 다른 종목 점수를 깎지 않음" 취지였으나, 이는 틀린 설명이다.
  - z-score는 평균과 표준편차를 사용하므로 극단값이 다른 종목의 점수 분포를 압축하거나 왜곡할 수 있다고 명시했다.
  - 1차 구현에서는 winsorize/clip 없이 z-score를 쓰되, 극단값이 있어도 낮은 부채비율 종목이 높은 점수를 받는 최소 방향성 테스트를 추가하도록 plan에 반영했다.
- Review #6 반영:
  - `combine_scores`가 각 컴포넌트에 `fillna(0.0)`을 적용한다는 현 동작을 plan에 명확히 적었다.
  - quality_score가 NaN이어도 total_score에는 중립점 0으로 반영될 수 있으므로, Task 1 spec에서 이 정책을 유지할지 변경할지 명시적으로 결정하도록 보강했다.
  - 정책 유지 시 "quality 데이터가 없는 종목도 value/momentum 기준으로 랭킹될 수 있음"을 테스트에 명시하도록 했다.
  - 정책 변경 시 shared behavior 변경이므로 기존 value/momentum 결측 테스트까지 함께 갱신해야 한다고 기록했다.

### 검증 결과

```text
pytest tests/factors -q -p no:cacheprovider
10 passed
```

### 남은 우선순위

- Review #7: ROE 분기 데이터 TTM 환산 여부 결정
- Review #8: 손절과 트레일링 동시 트리거 시 우선순위 명시
- Review #9: 손절 후 재진입 금지 옵션 결정
- Review #10~#15: 나머지 문서/작업 단위 보강

## 2026-05-04 Review #7~#15 반영 완료

### 처리한 작업

- Review #7 반영:
  - Phase 1 quality plan에 ROE/영업이익률 기간 정의를 확정했다.
  - ROE는 `TTM 당기순이익 / 평균자본총계`로 정의했다.
  - 영업이익률은 `TTM 영업이익 / TTM 매출액`으로 정의했다.
  - 부채비율은 TTM 환산하지 않고 최신 분기 재무상태표 스냅샷을 사용하기로 했다.
  - Phase 2 plan에는 Phase 1에서 저장된 TTM 결과값을 점수화만 한다고 명시했다.
- Review #8 반영:
  - Phase 3 stops plan에 손절과 트레일링이 동시에 충족될 때 `stop_loss`를 우선한다고 명시했다.
  - 테스트 케이스 `test_run_backtest_prefers_stop_loss_when_both_stops_trigger`를 추가하도록 plan을 보강했다.
- Review #9 반영:
  - 손절/트레일링 체결 당일에는 같은 종목 재진입을 금지한다.
  - N영업일 cooldown은 1차 구현에 넣지 않고, 실데이터 백테스트 결과를 본 뒤 별도 plan으로 결정하기로 했다.
  - 체결 당일 재진입 금지 테스트를 추가하도록 plan을 보강했다.
- Review #10 반영:
  - Phase 1 quality plan의 Task 2/3 분리 이유를 명시했다.
  - Task 2는 `quality_metrics` 데이터 저장 책임, Task 3은 `quality_sync_runs` 실행 이력 책임으로 분리한다고 기록했다.
- Review #11 반영:
  - Phase 2 plan의 loguru 설명을 수정했다.
  - loguru 기본 sink는 일반적으로 stderr이므로 stdout 단언에 영향이 없어야 한다고 적고, stderr 캡처 테스트에서는 설정 조정이 필요하다고 명시했다.
- Review #12 반영:
  - Phase 3 plan의 코드 스니펫/예시에서 생략 기호 `...`를 제거하고 구체적인 예시 값과 설명으로 대체했다.
- Review #14 반영:
  - 신규 4개 plan 모두에 `Plan dependencies` 섹션을 추가하거나 보강했다.
  - 각 plan의 선행/후행/독립 관계와 권장 commit scope를 명시했다.
- Review #15 반영:
  - handoff 문서에 Git commit 단위 가이드를 추가했다.
  - ZIP 다운로드본이라 `.git` 연결이 없을 수 있음을 전제로, Git 연결 후 커밋을 작게 나누는 기준을 기록했다.

### 업데이트한 문서

- `docs/superpowers/plans/2026-05-04-phase1-quality-fundamentals.md`
- `docs/superpowers/plans/2026-05-04-phase2-quality-score.md`
- `docs/superpowers/plans/2026-05-04-phase3-stops-simulation.md`
- `docs/superpowers/plans/2026-05-04-cost-parameters-recheck.md`
- `docs/superpowers/2026-05-04-handoff.md`

### 검증 결과

```text
pytest -q -p no:cacheprovider
33 passed
```

### 현재 상태

- Review #1~#15 문서 반영은 모두 완료됐다.
- 다음은 실제 구현 착수 단계다.
- 권장 구현 순서:
  1. 거래세/비용 재검토 plan
  2. Phase 3 손절/트레일링 백테스트 plan
  3. Phase 1 DART quality fundamentals plan
  4. Phase 2 quality score plan

## 2026-05-04 12:37 KST Plan Mode 저장

### 사용자 요청

- 현재는 실제 코드 구현이 아니라 Plan mode로 진행한다.
- 여러 항목을 한꺼번에 뭉뚱그려 진행하지 않는다.
- 선택이 필요한 부분은 사용자에게 질문하고, 사용자가 객관적으로 판단할 수 있도록 자세히 설명한다.

### 추가 검토 후보

앞서 추가로 검토할 만한 내용으로 다음을 제안했다.

1. 백테스트 look-ahead bias
2. 생존편향
3. 백테스트 수량의 정수 주식 처리
4. 리밸런싱/stop 체결 가격 기준 통일
5. DART 라이브러리 버전 재검토
6. 거래세 출처 공식/준공식 고정
7. DART 정정공시/restatement 정책
8. 리밸런싱 빈도 비교
9. turnover 및 비용 민감도 성과지표 추가
10. `.venv`와 `venv` 환경 경로 표준화

### 현재 진행 중인 검토 항목

- 1번: 백테스트 look-ahead bias 검토를 시작했다.
- 아직 사용자의 최종 선택은 받지 않았다.
- 코드 변경은 하지 않았다.

### 백테스트 look-ahead bias 설명 요약

Look-ahead bias는 백테스트가 그 시점에는 아직 알 수 없던 정보를 사용해 매매하는 문제다.

현재 Phase 3 구조는 같은 날짜의 가격/팩터를 보고 같은 날짜에 매수/매도하는 흐름이 될 수 있다. 실제 운영 계획은 장 시작 전 리밸런싱이므로, 전날까지 확정된 데이터로 오늘 아침 판단하고 오늘 체결하는 구조가 더 현실적이다.

### 사용자에게 제시한 선택지

1. 선택지 A: 현재 방식 유지
   - 당일 데이터로 신호 계산 후 당일 종가 체결.
   - 구현은 단순하지만 look-ahead bias 가능성이 크다.
   - 추천하지 않음.
2. 선택지 B: 전일 데이터로 신호 계산, 다음 거래일 시가 체결
   - `T-1` 종가/재무 데이터로 신호 계산 후 `T`일 시가에 매수/매도.
   - `T`일 종가로 equity_curve 평가.
   - 실제 `08:30` 리밸런싱 운영과 가장 잘 맞는다.
   - 추천안.
3. 선택지 C: 전일 데이터로 신호 계산, 다음 거래일 종가 체결
   - look-ahead bias는 줄지만 실제 장 시작 전 주문과는 덜 맞다.
   - open 데이터 품질이 불안정할 때 차선책.

### 현재 추천안

추천은 선택지 B다.

정책 문장 초안:

```text
백테스트 신호는 execution_date 직전 거래일까지 확정된 데이터로만 계산한다.
리밸런싱 매수/매도는 execution_date의 시가 기준으로 체결한다.
당일 장 마감 후 equity_curve는 execution_date의 종가 기준으로 평가한다.
```

### 다음에 이어서 할 일

- 사용자에게 선택지 A/B/C 중 하나를 확정받는다.
- 사용자가 선택하면 해당 정책을 Phase 3 plan/spec에 문서로 반영한다.
- 아직 구현은 하지 않는다.

## 2026-05-04 매수 조건 보강 논의

### 확정된 방향

- 백테스트 look-ahead bias 정책은 B안을 채택한다.
  - 전일 데이터로 신호 계산
  - 다음 거래일 시가 기준 체결
  - 당일 종가 기준 평가
- 재무제표 quality 데이터는 `published_at <= signal_date`인 데이터만 사용한다.
- `published_at`이 없는 재무제표 데이터는 사용하지 않는다.
- quality 데이터가 없는 종목 처리 정책은 C안으로 진행을 목표로 한다.
  - 점수 계산은 가능하게 하되, 포트폴리오 편입은 quality 커버리지 조건을 만족할 때만 허용하는 방향.
  - 개별 종목은 ROE, 영업이익률, 부채비율 3개 중 최소 2개 이상 있어야 quality 검증 종목으로 인정.
  - 최종 후보군의 quality 검증 종목 비율이 70% 이상이면 quality 필터를 활성화.
  - quality 필터 활성화 시 ROE > 0, 부채비율 < 300% 조건을 만족해야 신규 매수 가능.
  - quality 커버리지 70% 미만이면 quality 필터는 신규 매수 제외 조건으로 쓰지 않고 경고 로그만 남긴 뒤 value/momentum 중심으로 운용.
  - 사용자 선택: 70% 이상 균형형.

### 사용자가 추가 요청한 매수 필터 후보

1. 유동성 필터
   - 최근 20거래일 평균 거래대금이 20억 원 미만인 종목 제외.
   - 사용자 선택: 20억 원 이상 균형형.
2. 가격 필터
   - 1주 가격이 1,000원 미만인 종목 제외.
3. 거래정지/유의 종목 제외
   - 거래정지, 관리, 투자주의/경고/위험 등 자동매매에 부적합한 종목 제외.
   - KRX 공식 데이터를 우선 사용.
   - 상태 정보가 확인되지 않는 종목은 보수적으로 신규 매수 제외.
   - 사용자 선택: 상태 미확인 종목은 제외.
4. PER/PBR 음수 제외
   - PER <= 0 또는 PBR <= 0 종목 제외.
   - 사용자 선택: 0 이하 제외.
5. 최근 2분기 심한 적자 기업 제외
   - 최근 2개 분기 연속 영업이익률 < -10%이면 제외.
   - 또는 최근 2개 분기 연속 순이익률 < -10%이면 제외.
   - 사용자 선택: 균형형.
6. 퀄리티 최소 조건
   - ROE > 0
   - 부채비율 < 300%
7. 갭/급등락 필터
   - 오늘 시가가 전일 종가 대비 +20% 이상이면 신규 매수 제외.
   - 오늘 시가가 전일 종가 대비 -20% 이하이면 신규 매수 제외.
   - 즉 신규 매수는 `abs(today_open / previous_close - 1) < 0.20`인 종목만 허용.
   - 사용자 선택: 오늘 시가 vs 전일 종가 기준.
8. 상장 후 기간 필터
   - 상장 후 1년 미만 종목 제외.
   - 상장일은 KRX 공식 데이터를 우선 조회.
   - 상장일 확인 시 상장 후 365일 미만이면 신규 매수 제외.
   - 상장일이 확인되지 않는 종목은 신규 매수 후보에 남기되 warning 로그에 `listing_date_unknown` 기록.
   - 사용자 선택: 상장일 미확인 종목은 경고 후 통과.

### 다음에 결정해야 할 세부값

- 유동성 필터의 기준: 완료.
  - 최근 20거래일 평균 거래대금 >= 20억 원.
- quality 커버리지 C안의 기준:
  - 완료.
  - 개별 종목은 ROE, 영업이익률, 부채비율 중 최소 2개 이상 필요.
  - 최종 후보군 quality 검증 비율이 70% 이상이면 quality 필터 활성화.
- 최근 2분기 심한 적자 기준: 완료.
  - 최근 2개 분기 연속 영업이익률 < -10%이면 제외.
  - 또는 최근 2개 분기 연속 순이익률 < -10%이면 제외.
- PER/PBR 필터에서 0도 제외할지 여부: 완료.
  - PER <= 0 제외.
  - PBR <= 0 제외.
- 거래정지/유의 종목 정보를 어떤 데이터 소스에서 가져올지.
  - KRX 공식 데이터를 우선 사용.
  - 상태 정보 미확인 종목은 신규 매수 제외로 확정.
- 상장일 정보를 어떤 데이터 소스에서 가져올지.
  - KRX 공식 데이터를 우선 사용.
  - 상장일 미확인 종목은 경고 후 통과로 확정.

### 별도 정책 문서 생성

- 다른 AI 에이전트가 바로 이어받을 수 있도록 매수 필터 정책을 별도 spec 문서로 정리했다.
- 문서 위치:
  - `docs/superpowers/specs/2026-05-04-buy-filter-policy-design.md`
- 이 문서는 아직 구현 계획이 아니라 정책 설계 문서다.
- 향후 구현 전에는 별도 plan 문서를 만들고 TDD로 진행해야 한다.

## 2026-05-04 2차 기술적 진입 필터 정책

### 사용자 결정

- 1차 buy filter 이후 2차 필터로 기술적 분석 기반 진입 타이밍 필터를 둔다.
- 기술적 분석은 수익률 예측 도구가 아니라 나쁜 진입 타이밍을 피하는 risk/timing filter로 사용한다.
- 초기 MVP는 4개 조건 중 3개 이상 만족하면 통과하는 방식으로 진행한다.

### 확정된 MVP 조건

1. `signal_close > MA20`
   - 단기 추세가 살아 있는 종목만 신규 매수.
2. `MA60_today > MA60_20_trading_days_ago`
   - 중기 추세가 꺾인 종목 제외.
3. `RSI(14) < 75`
   - 과열 종목 추격매수 방지.
4. `20일 일간 수익률 표준편차 < 5%`
   - 변동성이 과도한 종목 제외.

### 통과 기준

```text
4개 조건 중 3개 이상 만족하면 통과.
2개 이하 만족하면 신규 매수 제외.
```

### 타이밍 정책

- 기술적 지표는 `signal_date`까지 확정된 가격 데이터로만 계산한다.
- `execution_date` 당일 종가는 사용하지 않는다.
- B안 백테스트 정책과 동일하게 신규 매수 체결은 `execution_date` 시가 기준이다.

### 별도 정책 문서

- 다른 AI 에이전트가 바로 이어받을 수 있도록 기술적 진입 필터 정책을 별도 spec 문서로 정리했다.
- 문서 위치:
  - `docs/superpowers/specs/2026-05-04-technical-entry-filter-policy-design.md`
- 아직 구현 계획이 아니라 정책 설계 문서다.

## 2026-05-04 프로젝트 정리/중복 후보 검토

### 명확하게 정리한 항목

- Python 실행/테스트가 생성한 캐시를 제거했다.
  - `__pycache__/`
  - `*.pyc`
  - `.pytest_cache/`
- `.gitignore`에 `venv_broken*/` 패턴을 추가했다.
  - 깨진 백업 가상환경이 Git에 올라가는 것을 방지하기 위함.

### 삭제 전 확인이 필요한 항목

- `venv_broken_py314/`
  - Python 3.14로 만들어졌다가 깨진 가상환경 백업.
  - 현재 정상 환경은 `venv/`이므로 실사용에는 필요 없다.
  - 다만 폴더 삭제는 되돌리기 어려우므로 사용자 확인 후 삭제하는 것이 좋다.
- `AGENTS.md`와 `CLAUDE.md`
  - 파일 내용과 해시가 동일하다.
  - 다만 서로 다른 AI 도구가 각각 찾는 파일명일 수 있어, 중복이어도 유지하는 쪽이 안전하다.

### 유지해야 하는 항목

- `docs/superpowers/plans/2026-05-03-*`
  - 새 plan들과 일부 중복처럼 보일 수 있지만, 기존 구현의 근거와 이력이다.
  - 삭제하지 않는 것이 좋다.
- `progress.md`
  - 작업 인수인계와 의사결정 기록의 중심 문서다.
  - 길어지고 있지만 현재는 유지한다.

## 2026-05-04 프로젝트 정리/중복 후보 처리 추가

### 사용자 승인 후 삭제한 항목

- `venv_broken_py314/`
  - Python 3.14 기반으로 만들어졌던 깨진 가상환경 백업 폴더.
  - 현재 프로젝트 실행/테스트는 Python 3.12 기반 `venv/`를 사용하므로 유지 필요성이 낮다고 판단했다.
  - 사용자의 삭제 승인 후 프로젝트 루트 내부 경로임을 확인하고 삭제했다.

### 유지하기로 한 중복 후보

- `AGENTS.md`와 `CLAUDE.md`
  - 두 파일 내용은 동일하지만, 서로 다른 AI 도구가 각자 다른 파일명을 자동 탐색할 가능성이 있다.
  - 단순 중복처럼 보이더라도 협업/인수인계 목적상 유지하는 편이 안전하다고 판단했다.
