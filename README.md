# quntbot

코스피·코스닥 개별 종목 **3-팩터 퀀트 자동매매 봇**.

> 한국투자증권 KIS API 기반 / 가치·퀄리티·모멘텀 / 스윙 / 모의투자 우선

---

## 폴더 구조

```
quntbot/
├── config.py              # 모든 파라미터 한곳 (자금·손절·팩터 가중치)
├── requirements.txt       # 의존성
├── .env.example           # 환경변수 템플릿 (.env 로 복사 후 채우기)
├── src/
│   ├── data/              # Phase 1: 종목·시세·재무 수집·저장
│   ├── factors/           # Phase 2: 가치/퀄리티/모멘텀 점수 계산
│   ├── backtest/          # Phase 3: 5년치 시뮬레이션
│   ├── trading/           # Phase 4: KIS 주문·손절·트레일링
│   └── notify/            # Phase 5: 텔레그램·대시보드
├── data/                  # SQLite DB (.gitignore)
├── logs/                  # 로그 파일
├── tests/                 # 단위 테스트
└── scripts/               # 일회성 실행 스크립트
```

---

## 시작 (Phase 0: 환경 셋업)

### 1. 가상환경 만들기

```powershell
# Windows PowerShell
cd C:\Users\USER\Downloads\quant\quntbot
python -m venv venv
.\venv\Scripts\activate
```

성공하면 프롬프트 앞에 `(venv)` 가 붙어요.

### 2. 패키지 설치

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. 환경변수 파일 생성

```powershell
copy .env.example .env
```

`.env` 를 메모장으로 열어서 KIS API 키를 채워요. (Phase 4 들어갈 때까지는 비워둬도 동작은 OK)

### 4. 설정값 확인

```powershell
python config.py
```

JSON 으로 모든 설정이 출력되고 `[OK] 설정 일관성 통과` 가 보이면 환경 셋업 완료.

---

## 운영 모드

`.env` 의 `TRADE_MODE` 로 전환:

| 모드 | 의미 | 사용 시점 |
|---|---|---|
| `PAPER` | 모의투자 (가짜 돈) | **항상 여기서 시작** |
| `LIVE` | 실전 매매 (진짜 돈) | 모의투자 1~2개월 검증 후 |

---

## 안전장치

봇 코드에 박혀 있는 가드레일 (`config.py: SAFETY`):

- 일일 매매 횟수 한도: 매수 10 / 매도 10
- 일일 손실 한도: -3% 도달 시 당일 매매 중단
- 체결 실패 3회 재시도 후 실패 시 텔레그램 긴급 알림
- 모든 주문 전 잔고·예수금 확인
- API 키는 `.env` 분리 (Git 커밋 금지)

---

## 매매 전략

`config.py: FACTOR` / `EXIT_RULES`:

- **3-팩터 점수**: 가치(PER, PBR) + 퀄리티(ROE, 영업이익률, 부채비율) + 모멘텀(6M 수익률)
- **유니버스**: 코스피200 + 코스닥150 (관리·우선주 제외)
- **포지션**: 20종목 균등 분할
- **매도 (3중)**:
  1. 매일 리밸런싱 시 점수 하위로 밀려나면 교체
  2. 매수가 대비 -8% 시 즉시 손절
  3. 보유 후 최고가 대비 -10% 시 트레일링 스톱

---

## 다음 단계

Phase 0 완료 → Phase 1 (데이터 파이프라인) 으로 진행.

자세한 의사결정 기록은 `interview-summary.md` 참고.
