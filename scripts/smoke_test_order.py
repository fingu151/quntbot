"""KIS PAPER order smoke test: paper buy, then immediate paper sell.

Usage:
    python scripts/smoke_test_order.py

Notes:
    - PAPER only. KisClient blocks LIVE mode.
    - Buys 1 share of Samsung Electronics (005930), then sells it.
    - This is still a real paper-account order.
"""
import argparse
import sys
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger

from config import TRADE_MODE
from src.trading.kis_client import KisClient

TICKER = "005930"   # Samsung Electronics
QTY = 1             # 1 share
KST = ZoneInfo("Asia/Seoul")
MARKET_OPEN = time(9, 0)
MARKET_CLOSE_GUARD = time(15, 20)


def is_regular_market_time(now: datetime | None = None) -> bool:
    current = now or datetime.now(KST)
    current = current.astimezone(KST)
    return current.weekday() < 5 and MARKET_OPEN <= current.time() <= MARKET_CLOSE_GUARD


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a PAPER order smoke test.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Place the paper order even outside the conservative regular-market window.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, now: datetime | None = None) -> int:
    args = parse_args(argv)

    logger.info("=" * 50)
    logger.info("KIS PAPER order smoke test started")
    logger.info("=" * 50)
    logger.info(f"TRADE_MODE : {TRADE_MODE}")
    logger.info(f"Ticker     : {TICKER} (Samsung Electronics)")
    logger.info(f"Quantity   : {QTY} share / market order")

    if not args.force and not is_regular_market_time(now):
        logger.error(
            "Order smoke test is blocked outside 09:00-15:20 KST on weekdays. "
            "Use --force only when you intentionally want to test order rejection or after-hours behavior."
        )
        return 1

    client = KisClient()

    # 1. Check balance before order.
    logger.info("-" * 40)
    logger.info("[STEP 1] Check balance before order")
    before = client.get_balance()
    if before.get("rt_cd") != "0":
        logger.error(f"Balance lookup failed: {before.get('msg1')}")
        return 1
    output2_before = (before.get("output2") or [{}])[0]
    cash_before = int(output2_before.get("dnca_tot_amt", 0))
    logger.success(f"Cash before order: {cash_before:,} KRW")

    # 2. Place buy order.
    logger.info("-" * 40)
    logger.info(f"[STEP 2] Buy order ({TICKER} {QTY} share market)")
    buy_result = client.place_order(TICKER, qty=QTY, price=0, side="BUY")
    rt_cd_buy = buy_result.get("rt_cd")
    if rt_cd_buy != "0":
        logger.error(f"Buy order failed: rt_cd={rt_cd_buy}, msg={buy_result.get('msg1')}")
        return 1
    order_no = buy_result.get("output", {}).get("ODNO", "N/A")
    logger.success(f"Buy order accepted. order_no={order_no}")

    # 3. Place sell order.
    logger.info("-" * 40)
    logger.info(f"[STEP 3] Sell order ({TICKER} {QTY} share market)")
    sell_result = client.place_order(TICKER, qty=QTY, price=0, side="SELL")
    rt_cd_sell = sell_result.get("rt_cd")
    if rt_cd_sell != "0":
        logger.error(f"Sell order failed: rt_cd={rt_cd_sell}, msg={sell_result.get('msg1')}")
        return 1
    order_no_sell = sell_result.get("output", {}).get("ODNO", "N/A")
    logger.success(f"Sell order accepted. order_no={order_no_sell}")

    logger.info("=" * 50)
    logger.success("ORDER SMOKE TEST PASSED")
    logger.info("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
