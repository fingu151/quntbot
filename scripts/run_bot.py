"""quntbot 자동매매 봇 실행 진입점.

실행:
    python scripts/run_bot.py

종료:
    Ctrl+C
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger

import config
from config import KIS, LOG_FILE, LOG_LEVEL, TRADE_MODE


def _setup_logging() -> None:
    logger.remove()
    logger.add(sys.stderr, level=LOG_LEVEL)
    logger.add(LOG_FILE, level=LOG_LEVEL, rotation="1 day", retention="30 days", encoding="utf-8")


def _preflight_check() -> None:
    """시작 전 설정 유효성 검사. 문제가 있으면 즉시 종료."""
    issues = config.validate()
    if issues:
        for w in issues:
            logger.error(f"설정 오류: {w}")
        sys.exit(1)

    missing = []
    if not KIS.app_key:
        missing.append("KIS_APP_KEY")
    if not KIS.app_secret:
        missing.append("KIS_APP_SECRET")
    if not KIS.account_no:
        missing.append("KIS_ACCOUNT_NO")
    if missing:
        logger.error(f".env에 다음 값이 비어 있습니다: {', '.join(missing)}")
        sys.exit(1)

    if TRADE_MODE != "PAPER":
        logger.error(
            f"TRADE_MODE={TRADE_MODE!r} — 현재는 PAPER 모드만 허용됩니다. "
            f".env에서 TRADE_MODE=PAPER 로 설정하세요."
        )
        sys.exit(1)


def main() -> None:
    _setup_logging()

    logger.info("=" * 50)
    logger.info("quntbot 시작")
    logger.info("=" * 50)
    logger.info(f"TRADE_MODE : {TRADE_MODE}")
    logger.info(f"BASE_URL   : {KIS.base_url}")
    logger.info(f"ACCOUNT_NO : {KIS.account_no[:4]}****")

    _preflight_check()

    from src.trading.scheduler import run_scheduler
    run_scheduler()


if __name__ == "__main__":
    main()
