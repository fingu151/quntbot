"""Telegram notifications for order, risk, and error events."""
from __future__ import annotations

import requests
from loguru import logger

from config import TELEGRAM, TelegramConfig


class TelegramNotifier:
    """Send Telegram bot messages.

    When Telegram is not configured, notifications are treated as no-ops so
    trading logic can continue safely in local or test environments.
    """

    def __init__(self, config: TelegramConfig = TELEGRAM) -> None:
        self._config = config

    def send(self, message: str) -> bool:
        """Send a Telegram message.

        Returns True when the message was sent, or when Telegram is disabled.
        Returns False on network/API errors without interrupting trading logic.
        """
        if not self._config.enabled:
            logger.debug(f"[notification disabled] {message}")
            return True

        url = f"https://api.telegram.org/bot{self._config.bot_token}/sendMessage"
        payload = {
            "chat_id": self._config.chat_id,
            "text": message,
            "parse_mode": "HTML",
        }
        try:
            resp = requests.post(url, json=payload, timeout=5)
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.warning(f"Telegram send failed; continuing: {self._safe_error_message(exc)}")
            return False

    def _safe_error_message(self, exc: Exception) -> str:
        message = str(exc)
        if self._config.bot_token:
            message = message.replace(self._config.bot_token, "<TELEGRAM_BOT_TOKEN>")
        if self._config.chat_id:
            message = message.replace(self._config.chat_id, "<TELEGRAM_CHAT_ID>")
        return message

    def notify_order(
        self,
        side: str,
        ticker: str,
        name: str,
        qty: int,
        price: int,
        order_no: str,
    ) -> None:
        action = "매수" if side == "BUY" else "매도"
        price_str = f"{price:,}원" if price > 0 else "시장가"
        self.send(
            f"[PAPER 주문 접수] {action}\n"
            f"종목: {name}({ticker})\n"
            f"수량: {qty}주\n"
            f"가격: {price_str}\n"
            f"주문번호: {order_no}"
        )

    def notify_stop_loss(
        self,
        ticker: str,
        name: str,
        qty: int,
        pnl_rate: float,
    ) -> None:
        self.send(
            "[리스크] 손절/트레일링 매도 실행\n"
            f"종목: {name}({ticker})\n"
            f"수량: {qty}주\n"
            f"손익률: {pnl_rate:.2%}"
        )

    def notify_daily_loss_halt(self, pnl_rate: float) -> None:
        self.send(
            "[긴급] 일일 손실 한도 초과\n"
            "당일 매매를 중단합니다.\n"
            f"현재 손익률: {pnl_rate:.2%}"
        )

    def notify_error(self, context: str, error: str) -> None:
        self.send(
            "[오류 발생]\n"
            f"위치: {context}\n"
            f"내용: {error}"
        )
