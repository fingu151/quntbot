"""리밸런싱 로직 — 현재 보유 종목과 목표 종목을 비교해 매도/매수 주문 목록을 생성."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from loguru import logger

from config import PORTFOLIO, SAFETY, PortfolioConfig


@dataclass(frozen=True)
class RebalanceOrder:
    """리밸런싱으로 생성된 단일 주문."""
    ticker: str
    side: str    # "BUY" 또는 "SELL"
    qty: int
    reason: str  # 주문 사유 (로그/알림용)


def compute_rebalance_orders(
    *,
    holdings: list[dict[str, Any]],
    target_tickers: list[str],
    prices: dict[str, int],
    previous_closes: dict[str, int | float] | None = None,
    cash: int,
    portfolio: PortfolioConfig = PORTFOLIO,
    sell_eligible_tickers: list[str] | set[str] | None = None,
    target_weights: dict[str, float] | None = None,
) -> tuple[list[RebalanceOrder], list[RebalanceOrder]]:
    """현재 보유 종목과 목표 종목을 비교해 매도/매수 주문 목록을 반환한다.

    Args:
        holdings:       KisClient.get_holdings() 반환값
        target_tickers: 팩터 점수 상위 N개 종목코드 (이미 정렬된 상태)
        prices:         {ticker: 현재가} 딕셔너리
        cash:           현재 예수금 (원)
        portfolio:      포트폴리오 설정

    Returns:
        (sells, buys) 튜플.
        sells: 목표에 없는 보유 종목 전량 매도 주문
        buys:  목표에 있지만 미보유인 종목 매수 주문
    """
    held_tickers = {h["ticker"] for h in holdings}
    target_set = set(target_tickers)
    sell_set = set(sell_eligible_tickers) if sell_eligible_tickers is not None else held_tickers - target_set

    # --- 매도 대상: 보유 중이지만 목표에 없는 종목 ---
    sells: list[RebalanceOrder] = []
    expected_sell_proceeds = 0
    for h in holdings:
        if h["ticker"] in sell_set:
            sells.append(RebalanceOrder(
                ticker=h["ticker"],
                side="SELL",
                qty=h["qty"],
                reason=f"rebalance sell buffer exit (holding {h['qty']} shares)",
            ))
            expected_sell_proceeds += int(h.get("current_price", 0) or 0) * int(h["qty"])
            logger.info(f"[리밸런서] 매도 예정: {h['name']}({h['ticker']}) {h['qty']}주")

    # --- 매수 대상: 목표에 있지만 미보유인 종목 ---
    # 균등배분: 예수금 / 매수 대상 수
    buy_targets = [t for t in target_tickers if t not in held_tickers]
    if not buy_targets:
        return sells, []

    available_cash = cash + expected_sell_proceeds
    weights = target_weights or {}

    buys: list[RebalanceOrder] = []
    for ticker in buy_targets:
        price = prices.get(ticker, 0)
        if price <= 0:
            logger.warning(f"[리밸런서] {ticker} 현재가 조회 불가 — 매수 건너뜀")
            continue

        previous_close = (previous_closes or {}).get(ticker)
        if is_execution_gap_too_large(
            execution_price=price,
            previous_close=previous_close,
            max_abs_gap_pct=portfolio.max_abs_open_gap_pct,
        ):
            gap_pct = (float(price) / float(previous_close)) - 1.0
            logger.warning(
                f"[rebalancer] {ticker} execution gap {gap_pct:.2%} exceeds "
                f"{portfolio.max_abs_open_gap_pct:.0%}; buy skipped"
            )
            continue

        if weights:
            budget = available_cash * max(weights.get(ticker, 0.0), 0.0)
        else:
            budget = available_cash / len(buy_targets)
        qty = math.floor(budget / price)
        if portfolio.enforce_price_filter and qty <= 0:
            logger.warning(
                f"[rebalancer] {ticker} price {price:,} exceeds budget {budget:,.0f}; buy skipped"
            )
            continue

        buys.append(RebalanceOrder(
            ticker=ticker,
            side="BUY",
            qty=qty,
            reason=f"target portfolio entry (budget {budget:,.0f} / {price:,} = {qty} shares)",
        ))
        logger.info(f"[리밸런서] 매수 예정: {ticker} {qty}주 ({price:,}원)")

    return sells, buys


def is_execution_gap_too_large(
    *,
    execution_price: int | float,
    previous_close: int | float | None,
    max_abs_gap_pct: float,
) -> bool:
    if previous_close is None or previous_close <= 0 or execution_price <= 0:
        return False
    gap_pct = (float(execution_price) / float(previous_close)) - 1.0
    return abs(gap_pct) > max_abs_gap_pct


def execute_rebalance(
    engine: Any,
    sells: list[RebalanceOrder],
    buys: list[RebalanceOrder],
    *,
    preflight_report_path: str | Path | None = None,
    expected_preflight_date: date | None = None,
    allow_buys: bool = True,
) -> dict[str, list[str]]:
    """compute_rebalance_orders 결과를 TradingEngine을 통해 실제 주문으로 실행한다.

    매도를 먼저 실행해 예수금을 확보한 뒤 매수를 진행한다.

    Args:
        engine: TradingEngine 인스턴스
        sells:  매도 주문 목록
        buys:   매수 주문 목록

    Returns:
        {"sold": [...], "bought": [...], "failed": [...]}
    """
    if preflight_report_path is not None:
        _assert_preflight_report_allows_orders(
            preflight_report_path,
            expected_preflight_date=expected_preflight_date,
            enforce_buy_limit=allow_buys,
            enforce_buy_price_checks=allow_buys,
        )

    result: dict[str, list[str]] = {"sold": [], "bought": [], "failed": []}
    if not allow_buys:
        buys = []

    # 매도 먼저
    for order in sells:
        try:
            resp = engine.sell(order.ticker, qty=order.qty, price=0)
            if resp.get("rt_cd") == "0":
                result["sold"].append(order.ticker)
                logger.info(f"[리밸런서] 매도 접수 완료: {order.ticker}")
            else:
                result["failed"].append(order.ticker)
                logger.error(f"[리밸런서] 매도 실패: {order.ticker} → {resp.get('msg1')}")
        except RuntimeError as e:
            result["failed"].append(order.ticker)
            logger.error(f"[리밸런서] 매도 한도 초과: {order.ticker} → {e}")

    # 매수
    for order in buys:
        try:
            resp = engine.buy(order.ticker, qty=order.qty, price=0)
            if resp.get("rt_cd") == "0":
                result["bought"].append(order.ticker)
                logger.info(f"[리밸런서] 매수 접수 완료: {order.ticker}")
            else:
                result["failed"].append(order.ticker)
                logger.error(f"[리밸런서] 매수 실패: {order.ticker} → {resp.get('msg1')}")
        except RuntimeError as e:
            result["failed"].append(order.ticker)
            logger.error(f"[리밸런서] 매수 한도 초과: {order.ticker} → {e}")

    logger.info(
        f"[리밸런서] 완료 — 매도 {len(result['sold'])}건 / "
        f"매수 {len(result['bought'])}건 / 실패 {len(result['failed'])}건"
    )
    return result


def _assert_preflight_report_allows_orders(
    report_path: str | Path,
    *,
    expected_preflight_date: date | None = None,
    enforce_buy_limit: bool = True,
    enforce_buy_price_checks: bool = True,
) -> None:
    path = Path(report_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("dry_run") is not True:
        raise RuntimeError(f"preflight report is not a dry-run report: {path}")

    if expected_preflight_date is not None:
        report_date = payload.get("as_of_date")
        if report_date != str(expected_preflight_date):
            raise RuntimeError(
                f"dry-run preflight blocked: stale report as_of_date={report_date!r}, "
                f"expected={expected_preflight_date}"
            )

    fallback_count = int(payload.get("price_fallback_count", 0) or 0)
    if enforce_buy_price_checks and fallback_count:
        tickers = [
            str(item.get("ticker", ""))
            for item in payload.get("price_fallbacks", [])
            if item.get("ticker")
        ]
        suffix = f" tickers={tickers}" if tickers else ""
        raise RuntimeError(
            f"dry-run preflight blocked: fallback prices were used ({fallback_count}).{suffix}"
        )

    failed_count = int(payload.get("price_lookup_failed_count", 0) or 0)
    if enforce_buy_price_checks and failed_count:
        tickers = [str(ticker) for ticker in payload.get("price_lookup_failures", [])]
        suffix = f" tickers={tickers}" if tickers else ""
        raise RuntimeError(
            f"dry-run preflight blocked: live price lookup failed ({failed_count}).{suffix}"
        )

    buy_count = int(payload.get("buy_count", 0) or 0)
    if enforce_buy_limit and buy_count > SAFETY.max_daily_buys:
        raise RuntimeError(
            "dry-run preflight blocked: daily buy limit would be exceeded "
            f"({buy_count}/{SAFETY.max_daily_buys})"
        )

    sell_count = int(payload.get("sell_count", 0) or 0)
    if sell_count > SAFETY.max_daily_sells:
        raise RuntimeError(
            "dry-run preflight blocked: daily sell limit would be exceeded "
            f"({sell_count}/{SAFETY.max_daily_sells})"
        )
