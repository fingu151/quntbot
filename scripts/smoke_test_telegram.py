from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import TELEGRAM, TelegramConfig
from src.notify.notifier import TelegramNotifier


NotifierFactory = Callable[[TelegramConfig], TelegramNotifier]
DEFAULT_MESSAGE = (
    "[quntbot 알림 테스트]\n"
    "텔레그램 알림 설정이 정상적으로 연결되었습니다.\n"
    "이 메시지는 주문을 실행하지 않는 smoke test입니다."
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send a Telegram notification smoke-test message without placing orders."
    )
    parser.add_argument("--message", default=DEFAULT_MESSAGE)
    return parser.parse_args(argv)


def run(
    args: argparse.Namespace,
    *,
    config: TelegramConfig = TELEGRAM,
    notifier_factory: NotifierFactory = TelegramNotifier,
) -> int:
    missing = []
    if not config.bot_token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not config.chat_id:
        missing.append("TELEGRAM_CHAT_ID")

    print(f"telegram_enabled={str(config.enabled).lower()}")
    print(f"bot_token_present={str(bool(config.bot_token)).lower()}")
    print(f"chat_id_present={str(bool(config.chat_id)).lower()}")
    if missing:
        print(f"missing={','.join(missing)}")
        return 1

    notifier = notifier_factory(config)
    sent = notifier.send(args.message)
    print(f"telegram_send_status={'ok' if sent else 'failed'}")
    print("orders_submitted=0")
    return 0 if sent else 1


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
