# Cost Parameters Decision

Date: 2026-05-06

## Decision

`config.COST` uses the following sell-side tax assumptions for Korean listed stocks:

- KOSPI: `tax_rate_kospi = 0.0020`
- KOSDAQ: `tax_rate_kosdaq = 0.0020`
- Commission remains `commission_rate = 0.00015`
- Slippage remains `slippage_rate = 0.0010`

## Source Check

Primary government source checked:

- Ministry of Economy and Finance / MOFE, "2025년 세제개편 후속 시행령 개정안", published 2026-01-16.
  https://www.moef.go.kr/nw/nes/detailNesDtaView.do?menuNo=4010100&searchBbsId1=MOSFBBS_000000000028&searchNttId1=MOSF_000000000076517

Supporting report checked:

- Yonhap syndicated report via Financial News, published 2025-12-01.
  https://www.fnnews.com/news/202512010901015399

The checked sources describe the 2026-01-01 change as:

- KOSPI securities transaction tax changes to 0.05%, while the 0.15% special rural tax remains. Total sell-side tax: 0.20%.
- KOSDAQ and K-OTC securities transaction tax changes from 0.15% to 0.20%. No special rural tax. Total sell-side tax: 0.20%.

## Rationale

The previous project default was `0.0018` for both KOSPI and KOSDAQ. That represented the older 0.18% assumption and would understate sell-side costs in 2026 backtests and live/PAPER reporting.

The bot currently trades only KOSPI/KOSDAQ candidates, so this change is limited to those two configured rates. KONEX and other markets are outside the current universe.

## Deferred Measurement

The plan called for measuring the backtest impact of 0.18% versus 0.20% on real DB data. That is deferred because `data/quntbot.db` is not present in this workspace yet. Running `scripts/run_phase3_backtest.py` against an empty DB would not measure real cost impact.

After Phase 1 data sync creates a populated DB, rerun the same backtest window twice and record:

- final equity
- total return
- trade count
- total sell-side cost

## Follow-Up TODO

- [ ] Confirm the user's actual KIS account commission tier before LIVE trading and update `commission_rate` if needed.
- [ ] After at least 50 PAPER fills, recalibrate `slippage_rate` from actual fill price versus expected price.
- [ ] Once `data/quntbot.db` exists, document measured 0.18% versus 0.20% backtest impact here.

