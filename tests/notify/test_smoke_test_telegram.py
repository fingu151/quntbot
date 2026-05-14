from unittest.mock import MagicMock

from config import TelegramConfig


def _enabled_config() -> TelegramConfig:
    return TelegramConfig(bot_token="test_token", chat_id="123456")


def _disabled_config() -> TelegramConfig:
    return TelegramConfig(bot_token="", chat_id="")


def test_run_blocks_when_telegram_config_is_missing(capsys):
    import scripts.smoke_test_telegram as smoke

    result = smoke.run(smoke.parse_args([]), config=_disabled_config())

    output = capsys.readouterr().out
    assert result == 1
    assert "telegram_enabled=false" in output
    assert "missing=TELEGRAM_BOT_TOKEN,TELEGRAM_CHAT_ID" in output


def test_run_sends_test_message_without_printing_secrets(capsys):
    import scripts.smoke_test_telegram as smoke

    notifier = MagicMock()
    notifier.send.return_value = True
    args = smoke.parse_args(["--message", "hello"])

    result = smoke.run(args, config=_enabled_config(), notifier_factory=MagicMock(return_value=notifier))

    output = capsys.readouterr().out
    assert result == 0
    assert "telegram_enabled=true" in output
    assert "telegram_send_status=ok" in output
    assert "test_token" not in output
    assert "123456" not in output
    notifier.send.assert_called_once_with("hello")


def test_run_reports_send_failure(capsys):
    import scripts.smoke_test_telegram as smoke

    notifier = MagicMock()
    notifier.send.return_value = False

    result = smoke.run(
        smoke.parse_args([]),
        config=_enabled_config(),
        notifier_factory=MagicMock(return_value=notifier),
    )

    assert result == 1
    assert "telegram_send_status=failed" in capsys.readouterr().out
