# Research Report Work Progress

작성일: 2026-05-13

이 문서는 quntbot 프로젝트에서 최근 진행한 대시보드/팩터 점수/증권사 리서치 리포트 연동 작업을 다른 환경으로 옮기기 위한 인수인계 기록입니다.

## 프로젝트 개요

quntbot은 국내 주식 종목을 대상으로 가치, 퀄리티, 모멘텀, 보조 신호를 합산해 종목을 선정하고, KIS API 기반 PAPER 매매를 우선으로 운영하는 퀀트 자동매매 프로젝트입니다.

주요 흐름은 다음과 같습니다.

1. `src/data`: 종목, 가격, 재무, 신호 데이터 수집 및 SQLite 저장
2. `src/factors`: 가치/퀄리티/모멘텀/보조 신호를 점수화
3. `src/trading`: 리밸런싱, 주문, 스케줄러, 안전장치
4. `scripts`: 동기화, 점수 산출, 대시보드, 운영용 실행 스크립트
5. `tests`: 단위 테스트 및 회귀 테스트

## 작업 규칙

작업 중 적용한 주요 규칙입니다.

- 코드 수정 전 관련 파일을 최소 5개 이상 읽고 진행
- 모르면 추측하지 않고 `rg`, 파일 읽기, DB 조회로 확인
- 변경 후 문법 검사, 테스트, 로그/DB 확인 중 최소 하나로 검증
- 한 번에 하나의 기능 단위로 변경
- 리서치 리포트/팩터 파라미터는 실제 DB row, 실행 결과, 테스트 결과를 근거로 판단
- 주문 관련 작업은 PAPER 안전 경로와 no-order dry-run을 우선
- `docs/agent-roster.md` 기준으로 작업 유형별 에이전트 역할을 적용

이번 리서치 리포트 작업에서는 `Research/Signal Ingestion` 역할을 리드로 보고, 테스트/검증 보조 에이전트를 붙여 설계 리스크와 테스트 범위를 확인했습니다.

## 지금까지 완료한 큰 작업

### 1. 대시보드 실행 확인

Streamlit 대시보드를 띄우려 했으나, 앱 브라우저에서 `127.0.0.1:8501 refused to connect` 문제가 발생했습니다.

확인 결과 Codex/WSL/Windows 실행 환경의 네트워크 네임스페이스 문제로 보이며, 이 작업은 중단하고 기능 개발 쪽으로 전환했습니다.

현재 상태:

- 대시보드 기능 자체 수정은 이번 작업의 핵심 범위가 아님
- 실행 문제는 별도 환경 복구 작업으로 남아 있음

### 2. 배당 점수 비중 조정

종목 선정 시 배당 점수 비중이 과하다고 판단해 절반 정도 줄였습니다.

변경 내용:

- `config.py`
  - `FactorConfig.yield_weight`: `0.5`에서 `0.25`로 축소
  - 줄인 `0.25`는 가치/퀄리티/모멘텀 쪽에 균등 배분

의도:

- 배당률이 높은 종목이 과도하게 유리해지는 현상 완화
- 다른 핵심 팩터의 변별력 강화

테스트:

- `tests/test_config.py`에 기본 가중치 검증 테스트 추가/수정

### 3. 총점 100점 체계 전환

기존 팩터 점수는 내부 정규화 점수 형태였고 직관성이 떨어졌습니다. 종목별 최종 점수를 100점 만점 기준으로 볼 수 있도록 바꿨습니다.

변경 내용:

- `src/factors/scoring.py`
  - `combine_scores(..., scale_to: float | None = None)` 옵션 추가
- `src/factors/engine.py`
  - 최종 `total_score`를 `scale_to=100.0` 기준으로 계산
- 관련 테스트 업데이트
  - `tests/factors/test_scoring.py`
  - `tests/factors/test_engine.py`

확인 결과:

- 2026-05-12 기준 상위권 점수는 대략 59~62점대 수준으로 확인됨
- 100점 만점이지만 실제 점수 분포는 데이터와 정규화 결과에 따라 중간 점수대에 모임

### 4. 리서치 리포트 신호 테이블 및 팩터 반영

증권사 리서치 리포트 내용을 종목 선정 점수에 보조 신호로 반영하는 구조를 추가했습니다.

추가/변경 파일:

- `src/data/models.py`
  - `ResearchReportSignal` 모델 추가
- `src/data/repositories.py`
  - `upsert_research_report_signals`
  - `get_recent_research_report_scores`
- `src/factors/models.py`
  - `research_report_score` 필드 추가
- `src/factors/engine.py`
  - 최근 리서치 리포트 점수를 팩터 계산에 반영
- `config.py`
  - `FactorConfig.research_report_weight = 0.25`

리서치 리포트 점수 반영 방식:

- `raw_score`는 기본적으로 `-1.0`부터 `1.0` 범위
- 최근 리포트일수록 더 크게 반영하는 recency weighting 구조
- 최종 팩터 점수에서는 작은 보조 가중치로 반영

관련 테스트:

- `tests/data/test_repositories.py`
- `tests/factors/test_engine.py`
- `tests/factors/test_rank_script.py`

### 5. 한경 컨센서스 연동 완료

한경 컨센서스를 기본 리서치 리포트 소스로 연결했습니다.

설정:

- `config.py`
  - `ResearchReportConfig`
  - 기본 URL: `https://markets.hankyung.com/consensus`
  - 기본 source: `hankyung_consensus`
  - 기본 broker: `한경 컨센서스`

수집 스크립트:

- `scripts/sync_korean_research_reports.py`
  - 기본값으로 한경 컨센서스를 수집

스케줄러:

- `src/trading/scheduler.py`
  - `_research_report_job`
  - 평일 06~09시 사이 30분 단위 수집 job 추가
  - 주문 실행 없음: `orders_submitted=0`

실제 DB 저장 확인:

```text
hankyung_consensus|10|2026-05-08|2026-05-13
```

샘플 저장 종목:

- `000370`
- `004170`
- `006400`
- `006800`
- `009830`
- `023530`
- `079550`
- `178320`
- `263750`

랭킹 확인:

```text
research_report_scored_count=1
research_report_coverage=0.5%
```

주의:

- 한경은 현재 동작하지만, 내부 Nuxt/페이지 구조를 파싱하는 방식이라 사이트 구조 변경에 취약할 수 있음

### 6. 미래에셋증권 연동

미래에셋증권 리서치 페이지는 일반 페이지 접근이 불안정했습니다.

확인 내용:

- `https://securities.miraeasset.com/newir/view/pc/kr/investor/researchReportsList.jsp`
  - HTTP 200이지만 내용이 비어 있는 형태로 확인
- 일반 게시판 URL 일부는 리다이렉트/로그인 게이트 가능성 있음
- 대신 공개 JS 파일은 접근 가능

사용한 공개 JS:

```text
https://securities.miraeasset.com/bbsdocs/bbs-html/home_bbsmain_new.js
```

파서 추가:

- `src/signals/research_report_parser.py`
  - `_parse_miraeasset_bbsdocs_reports`
  - `document.write('<li>...')` 형태의 공개 JS row 파싱
  - 제목, 종목코드, 날짜, 투자의견, PDF URL 추출

실제 DB 저장 확인:

```text
mirae_kr|4|2026-05-13|2026-05-13
```

미래에셋 저장 샘플:

```text
2026-05-13|145720|미래에셋증권|Buy|0.6|덴티움 (145720/매수)중국에서 2차 VBP만 다시 시작된다면!
2026-05-13|036570|미래에셋증권|Buy|0.6|NC (036570/매수)매수 타이밍. 모멘텀 구간 진입
2026-05-13|043150|미래에셋증권|Buy|0.6|바텍 (043150/매수)원가 압박 이겨내는 중
2026-05-13|112040|미래에셋증권|Buy|0.6|위메이드 (112040/매수)신작 출시 이후를 기대
```

주의:

- 현재 연결은 공개 JS 파일에 의존
- 공식 API가 아니므로 JS 파일 경로/형식이 바뀌면 파서 수정 필요

### 7. PDF 본문 인식 기능 1차 추가

사용자가 “제목만 보는 것이 아니라 내부 내용도 인식하는지”를 중요하게 봤기 때문에 PDF 본문 텍스트 인식 기능을 1차로 추가했습니다.

중요한 현재 상태:

- 기존에는 제목/목록 메타데이터만 점수화
- 이제 `--include-pdf-text` 옵션을 켜면 PDF 본문 텍스트를 읽어 점수에 반영하는 구조가 생김
- 리포트 전문은 DB에 저장하지 않음
- 본문에서 추출한 신호만 `rating`, `target_price`, `sentiment_score`, `raw_score`에 반영

변경 파일:

- `src/signals/research_report_parser.py`
  - `apply_report_body_text_signal(report, body_text)` 추가
  - PDF 본문에서 투자의견, 목표가, 긍정/부정 표현을 추출
  - 제목에 없는 값만 보완하고, 제목의 기존 정보를 무리하게 덮어쓰지 않음
  - 점수는 `-1.0`~`1.0` 범위로 clamp
- `src/signals/research_report_reader.py`
  - `fetch_pdf_text(url)` 추가
  - `pypdf.PdfReader`로 PDF 텍스트 추출
  - PDF 추출 실패 시 경고 로그만 남기고 기존 제목 기반 row 저장 유지
  - `include_pdf_text` 옵션 추가
- `scripts/sync_korean_research_reports.py`
  - `--include-pdf-text` CLI 옵션 추가
- `requirements.txt`
  - `pypdf==5.1.0` 추가

실행 예시:

```powershell
.\venv\Scripts\python.exe scripts\sync_korean_research_reports.py `
  --url "https://securities.miraeasset.com/bbsdocs/bbs-html/home_bbsmain_new.js" `
  --source mirae_kr `
  --broker "미래에셋증권" `
  --include-pdf-text
```

설계 의도:

- 스케줄러가 매번 PDF를 많이 다운로드하지 않도록 기본값은 꺼둠
- 본문 인식은 수동 실행이나 별도 검증 후 운영에 켜는 방식
- 저작권/용량 문제를 피하기 위해 전문 저장은 하지 않음

### 8. 리서치 리포트 점수 규칙

현재 리서치 리포트 점수는 다음 규칙을 따릅니다.

투자의견:

- Strong Buy: `1.0`
- Buy / Outperform: `0.6`
- Trading Buy: `0.4`
- Hold / Neutral / Market Perform: `0.0`
- Underperform / Reduce: `-0.6`
- Sell / Strong Sell: `-1.0`

목표가 변경:

- 목표가 20% 이상 상향: `+0.2`
- 목표가 소폭 상향: `+0.1`
- 목표가 20% 이상 하향: `-0.2`
- 목표가 소폭 하향: `-0.1`

본문/제목 감성 키워드:

- 긍정: `상향`, `올려`, `인상`, `개선`, `호조`, `저평가`, `undervalued`
- 부정: `하향`, `낮춰`, `인하`, `부진`, `고평가`, `부담`, `overvalued`, `downgrade`

최종 `raw_score`는 `-1.0`~`1.0`으로 제한합니다.

## 검증 내역

이미 통과한 주요 검증:

```text
tests/signals/test_research_report_parser.py
tests/signals/test_research_report_reader.py
```

초기 리서치 파서/reader 테스트:

```text
6 passed
```

리서치 관련 회귀 테스트:

```text
70 passed
```

전체 문법 검사:

```text
compileall config.py src scripts tests
```

마지막 PDF 본문 인식 추가 후 검증:

```text
python3 -m py_compile src/signals/research_report_parser.py src/signals/research_report_reader.py scripts/sync_korean_research_reports.py tests/signals/test_research_report_parser.py tests/signals/test_research_report_reader.py tests/signals/test_sync_korean_research_reports.py
```

통과.

본문 점수 스모크:

```text
body_target_signal_smoke=ok
```

주의:

- 마지막 단계에서 Windows venv 기반 `pytest`는 WSL 소켓 오류로 실행하지 못함
- 샌드박스 Python에는 `pytest`가 없어 전체 테스트는 마지막 변경 직후 재실행하지 못함
- PDF 본문 추출은 `pypdf` 설치 후 실제 PDF로 재검증 필요

## 현재 한계와 리스크

### 연결 안정성

한경 컨센서스:

- 현재 DB 저장까지 확인됨
- 다만 Nuxt 내부 데이터 구조에 의존하므로 페이지 구조 변경 시 깨질 수 있음

미래에셋증권:

- 일반 페이지는 비어 있거나 게이트가 걸릴 수 있음
- 현재는 공개 JS 파일을 사용하는 우회 방식
- 공개 JS 경로/HTML 구조 변경 시 수정 필요

### 본문 인식

현재 상태:

- PDF 텍스트 추출 함수와 점수 반영 구조는 추가됨
- 실제 운영 환경에 `pypdf` 설치 필요
- 리포트 PDF가 이미지 스캔 형태면 `pypdf`만으로 텍스트가 안 나올 수 있음

추후 필요할 수 있는 보강:

- OCR 처리
- PDF 본문 추출 성공률 로그
- 본문 텍스트 길이/추출 여부 DB 또는 로그 기록
- 리포트별 “본문 반영됨/실패함” 상태 필드

### 저작권/저장 정책

현재는 리포트 전문을 저장하지 않습니다.

이유:

- 증권사 리포트 전문은 저작권 이슈가 있을 수 있음
- DB 용량 증가
- 점수 산출에는 전문 저장보다 파생 신호 저장이 더 안전함

현재 저장하는 것은:

- 날짜
- 종목코드
- source
- broker
- 투자의견
- 목표가
- 감성 점수
- 원시 점수
- 제목
- PDF URL

## 다음에 해야 할 작업

우선순위 순서입니다.

1. 새 환경에서 의존성 설치

```powershell
pip install -r requirements.txt
```

2. PDF 본문 추출 실전 검증

```powershell
.\venv\Scripts\python.exe scripts\sync_korean_research_reports.py `
  --url "https://securities.miraeasset.com/bbsdocs/bbs-html/home_bbsmain_new.js" `
  --source mirae_kr `
  --broker "미래에셋증권" `
  --include-pdf-text
```

3. DB 저장 상태 확인

```powershell
sqlite3 data\quntbot.db "select source,count(*),min(report_date),max(report_date) from research_report_signals group by source;"
```

4. 본문 반영 여부를 로그로 확인

현재는 PDF 추출 실패 시 warning 로그만 남습니다. 성공률을 더 명확히 보려면 다음 필드/로그를 추가하는 것이 좋습니다.

- `pdf_text_attempted`
- `pdf_text_extracted`
- `pdf_text_length`
- `body_signal_applied`

5. 팩터 점수 재산출

```powershell
.\venv\Scripts\python.exe scripts\rank_phase2_factors.py --as-of-date 2026-05-13 --top-n 20
```

6. 전체 테스트 재실행

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

## 변경된 주요 파일 목록

설정:

- `config.py`
- `requirements.txt`

리서치 리포트 수집/파싱:

- `src/signals/research_report_parser.py`
- `src/signals/research_report_reader.py`
- `scripts/sync_korean_research_reports.py`

DB/팩터:

- `src/data/models.py`
- `src/data/repositories.py`
- `src/factors/models.py`
- `src/factors/engine.py`

스케줄러:

- `src/trading/scheduler.py`

대시보드/스냅샷:

- `scripts/rank_phase2_factors.py`
- `scripts/generate_public_portfolio_snapshot.py`
- `scripts/public_portfolio_dashboard.py`

테스트:

- `tests/test_config.py`
- `tests/data/test_repositories.py`
- `tests/factors/test_engine.py`
- `tests/factors/test_scoring.py`
- `tests/factors/test_rank_script.py`
- `tests/signals/test_research_report_parser.py`
- `tests/signals/test_research_report_reader.py`
- `tests/signals/test_sync_korean_research_reports.py`
- `tests/trading/test_scheduler.py`
- `tests/test_generate_public_portfolio_snapshot.py`
- `tests/test_public_portfolio_dashboard.py`

## 현재 결론

현재 리서치 리포트 기능은 다음 수준까지 진행됐습니다.

- 한경 컨센서스 목록 수집: 완료
- 미래에셋증권 공개 JS 목록 수집: 완료
- 리서치 리포트 신호 DB 저장: 완료
- 팩터 점수 반영: 완료
- 최종 점수 100점 체계: 완료
- PDF URL 저장: 완료
- PDF 본문 텍스트 추출 기능: 1차 구현 완료
- PDF 본문 기반 점수 반영: 1차 구현 완료
- 실제 PDF 본문 추출 운영 검증: 남음

다음 작업의 핵심은 `pypdf` 설치 후 실제 미래에셋/한경 PDF에서 본문 텍스트가 얼마나 잘 추출되는지 확인하고, 추출 성공률과 점수 반영 여부를 로그/DB에서 명확히 볼 수 있게 만드는 것입니다.
