# quntbot webapp

Toss Invest 스타일 프론트엔드 — `quntbot Design System`(claude.ai/design) 에서 가져온 UI 키트.
헤드리스 Python 엔진에 입히는 소비자용 화면 6종(자산·수익분석·거래내역·주문내역·예상 배당금·리포트).

## 실행

CDN(react/babel/폰트)을 쓰므로 `file://` 직접 열기 말고 http 서버로 띄웁니다.
**저장소 루트**에서 실행하세요 — 그래야 엔진이 만드는 `data/` 스냅샷도 같이 서빙됩니다.

```bash
# 저장소 루트(quntbot-main)에서
python -m http.server 5500
# → http://localhost:5500/webapp/ui_kits/toss-invest/index.html
```

## 실데이터 연동 (자동 반영)

화면은 엔진이 만드는 **`data/public_portfolio_snapshot.json`** 을 자동으로 읽습니다
(`ui_kits/toss-invest/snapshot.js` 어댑터).

- 스냅샷이 **있으면** → 자산·보유종목·팩터점수·랭크·체결상태·시장지수가 **실데이터**로 표시됩니다. (브라우저 콘솔에 `live snapshot loaded` 로그)
- 스냅샷이 **없으면** → `data.js` 의 mock 샘플로 자동 폴백합니다.

스냅샷은 엔진 스크립트로 생성/갱신됩니다(매수·매도가 반영되려면 이 갱신이 돌아야 함):

```bash
python -m scripts.generate_public_portfolio_snapshot          # 1회 생성
# 또는 주기 갱신 루프(30분):
powershell scripts/refresh_public_portfolio_snapshot.ps1
```

→ 새로고침하면 화면이 최신 스냅샷을 다시 읽습니다.

### 스냅샷이 채우는 화면 / 아직 mock인 화면

| 데이터 | 출처 |
|---|---|
| 자산(보유종목·평가금액·손익·팩터·랭크·체결), **주문내역(매수/매도)**, **리포트(리서치)**, 시장지수, 수익분석 팩터배분 | **스냅샷(실데이터)** |
| 거래내역 · 예상 배당금 · 섹터비중 · 평가금액 추이 | 아직 mock |

> 주문내역은 스냅샷의 `orders` 섹션(dry-run 주문 + 실행리포트 체결상태),
> 리포트는 `reports` 섹션(`research_report_analyses` DB + 종목명/목표가)에서 옵니다 —
> 모두 `scripts/generate_public_portfolio_snapshot.py` 가 생성.
> (DB가 없거나 리포트가 없으면 `reports`는 빈 배열이 되고, webapp은 mock 리포트로 폴백합니다.)
>
> 아직 mock인 항목의 정직한 사정:
> - **거래내역**: 체결 단가가 trade journal(CSV/DB)에만 있어 정적 JSON 소스 없음.
> - **예상 배당금**: 엔진에 배당 예측 산출물이 없음(배당수익률은 팩터 입력일 뿐).

## 구성

- `styles.css` + `tokens/` — 색·타이포·간격 토큰 (상승=빨강 / 하락=파랑 한국 시장 관례)
- `_ds_bundle.js` — 디자인 시스템 컴포넌트 (`window.QuntbotDesignSystem_ce5871`)
- `ui_kits/toss-invest/`
  - `index.html` — 진입점 (데이터 로드 후 마운트)
  - `data.js` — mock 샘플 (`window.QB_DATA`)
  - `snapshot.js` — 실데이터 어댑터 (스냅샷 → `QB_DATA`, 없으면 폴백)
  - `AppShell` · `icons` · 6개 화면
