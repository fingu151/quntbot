"""TelegramNotifier 단위 테스트."""
from unittest.mock import MagicMock, patch

from config import TelegramConfig
from src.notify.notifier import TelegramNotifier


def _enabled_config() -> TelegramConfig:
    return TelegramConfig(bot_token="test_token", chat_id="123456")


def _disabled_config() -> TelegramConfig:
    return TelegramConfig(bot_token="", chat_id="")


def test_send_returns_true_when_disabled():
    """텔레그램 미설정 시 send()는 True를 반환하고 HTTP 요청을 보내지 않는다."""
    notifier = TelegramNotifier(_disabled_config())
    with patch("src.notify.notifier.requests.post") as mock_post:
        result = notifier.send("test message")

    assert result is True
    mock_post.assert_not_called()


def test_send_posts_to_telegram_api():
    """텔레그램 설정이 있을 때 올바른 URL로 POST 요청을 보낸다."""
    notifier = TelegramNotifier(_enabled_config())
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()

    with patch("src.notify.notifier.requests.post", return_value=mock_resp) as mock_post:
        result = notifier.send("hello")

    assert result is True
    call_url = mock_post.call_args.args[0]
    assert "test_token" in call_url
    assert mock_post.call_args.kwargs["json"]["chat_id"] == "123456"


def test_send_returns_false_on_network_error():
    """네트워크 오류 시 예외를 삼키고 False를 반환한다 (매매 로직 중단 방지)."""
    notifier = TelegramNotifier(_enabled_config())
    with patch("src.notify.notifier.requests.post", side_effect=Exception("timeout")):
        result = notifier.send("test")

    assert result is False


def test_send_masks_secrets_in_error_logs():
    config = _enabled_config()
    notifier = TelegramNotifier(config)

    with (
        patch(
            "src.notify.notifier.requests.post",
            side_effect=Exception("https://api.telegram.org/bottest_token/sendMessage chat_id=123456"),
        ),
        patch("src.notify.notifier.logger.warning") as warning,
    ):
        result = notifier.send("test")

    message = warning.call_args.args[0]
    assert result is False
    assert "test_token" not in message
    assert "123456" not in message
    assert "<TELEGRAM_BOT_TOKEN>" in message
    assert "<TELEGRAM_CHAT_ID>" in message


def test_notify_order_formats_readable_buy_message():
    notifier = TelegramNotifier(_enabled_config())

    with patch.object(notifier, "send", return_value=True) as send:
        notifier.notify_order("BUY", "005930", "삼성전자", 3, 0, "0000001")

    message = send.call_args.args[0]
    assert "[PAPER 주문 접수] 매수" in message
    assert "종목: 삼성전자(005930)" in message
    assert "수량: 3주" in message
    assert "가격: 시장가" in message
    assert "주문번호: 0000001" in message


def test_notify_order_formats_readable_sell_message():
    notifier = TelegramNotifier(_enabled_config())

    with patch.object(notifier, "send", return_value=True) as send:
        notifier.notify_order("SELL", "005930", "삼성전자", 2, 70000, "0000002")

    message = send.call_args.args[0]
    assert "[PAPER 주문 접수] 매도" in message
    assert "가격: 70,000원" in message


def test_notify_risk_messages_are_readable():
    notifier = TelegramNotifier(_enabled_config())

    with patch.object(notifier, "send", return_value=True) as send:
        notifier.notify_stop_loss("005930", "삼성전자", 2, -0.082)
        notifier.notify_daily_loss_halt(-0.031)
        notifier.notify_error("test", "failure")

    messages = [call.args[0] for call in send.call_args_list]
    assert "[리스크] 손절/트레일링 매도 실행" in messages[0]
    assert "손익률: -8.20%" in messages[0]
    assert "[긴급] 일일 손실 한도 초과" in messages[1]
    assert "현재 손익률: -3.10%" in messages[1]
    assert "[오류 발생]" in messages[2]
