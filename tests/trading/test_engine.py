"""TradingEngine 단위 테스트."""
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config import ExitRulesConfig, SafetyConfig
from src.trading.engine import TradingEngine


# ------------------------------------------------------------------
# 헬퍼
# ------------------------------------------------------------------

def _make_engine(max_buys: int = 3, max_sells: int = 3,
                 daily_loss_limit: float = -0.03,
                 stop_loss_pct: float = -0.08,
                 daily_anchor_path: Path | None = None) -> TradingEngine:
    mock_client = MagicMock()
    mock_client.place_order.return_value = {"rt_cd": "0", "msg1": "주문접수"}

    safety = SafetyConfig(
        max_daily_buys=max_buys,
        max_daily_sells=max_sells,
        daily_loss_limit_pct=daily_loss_limit,
    )
    exit_rules = ExitRulesConfig(
        stop_loss_pct=stop_loss_pct,
        trailing_stop_pct=-0.10,
    )
    engine = TradingEngine(
        mock_client,
        safety=safety,
        exit_rules=exit_rules,
        daily_anchor_path=daily_anchor_path,
    )
    return engine


# ------------------------------------------------------------------
# 일일 한도 테스트
# ------------------------------------------------------------------

def test_buy_increments_daily_counter():
    """매수 성공 시 일일 매수 카운터가 1 증가한다."""
    engine = _make_engine()
    engine.buy("005930", qty=1)
    assert engine._daily_buys == 1


def test_sell_increments_daily_counter():
    """매도 성공 시 일일 매도 카운터가 1 증가한다."""
    engine = _make_engine()
    engine.sell("005930", qty=1)
    assert engine._daily_sells == 1


def test_buy_raises_when_daily_limit_reached():
    """일일 매수 한도 초과 시 RuntimeError 발생."""
    engine = _make_engine(max_buys=2)
    engine.buy("005930", qty=1)
    engine.buy("005930", qty=1)

    with pytest.raises(RuntimeError, match="일일 매수 한도 초과"):
        engine.buy("005930", qty=1)


def test_sell_raises_when_daily_limit_reached():
    """일일 매도 한도 초과 시 RuntimeError 발생."""
    engine = _make_engine(max_sells=1)
    engine.sell("005930", qty=1)

    with pytest.raises(RuntimeError, match="일일 매도 한도 초과"):
        engine.sell("005930", qty=1)


def test_counter_resets_on_new_day():
    """날짜가 바뀌면 일일 카운터와 halted 상태가 초기화된다."""
    engine = _make_engine(max_buys=1)
    engine.buy("005930", qty=1)
    assert engine._daily_buys == 1

    # 날짜를 어제로 조작해 리셋 트리거
    from datetime import timedelta
    engine._today = date.today() - timedelta(days=1)
    engine._reset_if_new_day()

    assert engine._daily_buys == 0
    assert engine._halted is False


# ------------------------------------------------------------------
# 일일 손실 한도 테스트
# ------------------------------------------------------------------

def test_check_daily_loss_first_check_sets_baseline_without_halt():
    """첫 손실 한도 체크는 당일 기준자산만 저장하고 중단하지 않는다."""
    engine = _make_engine(daily_loss_limit=-0.03)
    engine._client.get_balance.return_value = {
        "rt_cd": "0",
        "output2": [{"tot_evlu_amt": "95000000", "pchs_amt_smtl_amt": "100000000"}],
    }
    halted = engine.check_daily_loss_limit()
    assert halted is False
    assert engine._halted is False
    assert engine._daily_start_equity == 95000000


def test_check_daily_loss_reuses_same_day_anchor_after_restart(tmp_path):
    anchor_path = tmp_path / "daily_anchor.json"
    first_engine = _make_engine(daily_loss_limit=-0.03, daily_anchor_path=anchor_path)
    first_engine._client.get_balance.return_value = {
        "rt_cd": "0",
        "output2": [{"tot_evlu_amt": "100000000"}],
    }

    assert first_engine.check_daily_loss_limit() is False

    restarted_engine = _make_engine(daily_loss_limit=-0.03, daily_anchor_path=anchor_path)
    restarted_engine._client.get_balance.return_value = {
        "rt_cd": "0",
        "output2": [{"tot_evlu_amt": "97000000"}],
    }

    assert restarted_engine.check_daily_loss_limit() is True
    assert restarted_engine._daily_start_equity == 100_000_000


def test_check_daily_loss_ignores_previous_day_anchor_after_rollover(tmp_path):
    """며칠 살아있는 엔진의 새 날짜 첫 체크는 전날 기준자산을 쓰지 않는다."""
    import json
    from datetime import timedelta

    anchor_path = tmp_path / "daily_anchor.json"
    yesterday = date.today() - timedelta(days=1)
    anchor_path.write_text(
        json.dumps({"date": yesterday.isoformat(), "start_equity": 100_000_000}),
        encoding="utf-8",
    )

    engine = _make_engine(daily_loss_limit=-0.03, daily_anchor_path=anchor_path)
    engine._today = yesterday  # 전날부터 살아있는 엔진 시뮬레이션
    engine._client.get_balance.return_value = {
        "rt_cd": "0",
        "output2": [{"tot_evlu_amt": "95000000"}],  # 전날 대비 -5%, 당일 손실 0%
    }

    assert engine.check_daily_loss_limit() is False
    assert engine._daily_start_equity == 95_000_000
    assert engine._today == date.today()


def test_check_daily_loss_halts_when_intraday_drop_exceeds_limit():
    """당일 기준자산 대비 손실이 한도를 초과하면 halted=True 로 설정된다."""
    engine = _make_engine(daily_loss_limit=-0.03)
    engine._daily_start_equity = 100_000_000
    engine._client.get_balance.return_value = {
        "rt_cd": "0",
        "output2": [{"tot_evlu_amt": "95000000", "pchs_amt_smtl_amt": "100000000"}],
    }
    halted = engine.check_daily_loss_limit()
    assert halted is True
    assert engine._halted is True


def test_check_daily_loss_does_not_halt_within_limit():
    """당일 기준자산 대비 손실이 한도 이내이면 halted=False 를 유지한다."""
    engine = _make_engine(daily_loss_limit=-0.03)
    engine._daily_start_equity = 100_000_000
    engine._client.get_balance.return_value = {
        "rt_cd": "0",
        "output2": [{"tot_evlu_amt": "99000000"}],
    }
    halted = engine.check_daily_loss_limit()
    assert halted is False


def test_buy_raises_when_halted():
    """halted 상태에서 매수 시도 시 RuntimeError 발생."""
    engine = _make_engine()
    engine._halted = True

    with pytest.raises(RuntimeError, match="중단"):
        engine.buy("005930", qty=1)


# ------------------------------------------------------------------
# 손절 테스트
# ------------------------------------------------------------------

def test_check_stop_loss_triggers_sell_when_below_threshold():
    """수익률이 손절 기준(-8%) 이하인 종목을 시장가 매도한다."""
    engine = _make_engine(stop_loss_pct=-0.08)
    engine._client.get_holdings.return_value = [
        {"ticker": "005930", "name": "삼성전자", "qty": 5,
         "avg_price": 100000, "current_price": 88000,   # -12% → 손절
         "eval_profit_loss": -60000, "profit_loss_rate": -12.0},
    ]
    triggered = engine.check_stop_loss()
    assert "005930" in triggered
    engine._client.place_order.assert_called_once_with(
        "005930", qty=5, price=0, side="SELL"
    )


def test_check_stop_loss_does_not_trigger_above_threshold():
    """수익률이 손절 기준 이상이면 매도하지 않는다."""
    engine = _make_engine(stop_loss_pct=-0.08)
    engine._client.get_holdings.return_value = [
        {"ticker": "005930", "name": "삼성전자", "qty": 5,
         "avg_price": 100000, "current_price": 95000,   # -5% → 손절 미발생
         "eval_profit_loss": -25000, "profit_loss_rate": -5.0},
    ]
    triggered = engine.check_stop_loss()
    assert triggered == []
    engine._client.place_order.assert_not_called()


# ------------------------------------------------------------------
# 상태 조회 테스트
# ------------------------------------------------------------------

# ------------------------------------------------------------------
# 트레일링 스톱 테스트
# ------------------------------------------------------------------

def test_trailing_stop_updates_peak_price():
    """현재가가 최고가보다 높으면 최고가가 갱신된다."""
    engine = _make_engine()
    engine._client.get_holdings.return_value = [
        {"ticker": "005930", "name": "삼성전자", "qty": 5,
         "avg_price": 70000, "current_price": 90000,
         "eval_profit_loss": 0, "profit_loss_rate": 0},
    ]
    engine.check_trailing_stop()
    assert engine._peak_prices["005930"] == 90000


def test_trailing_stop_triggers_sell_when_below_threshold():
    """최고가 대비 낙폭이 trailing_stop_pct 이하면 매도한다."""
    engine = _make_engine(stop_loss_pct=-0.08)
    engine._peak_prices["005930"] = 100000  # 최고가 10만원 설정
    engine._client.get_holdings.return_value = [
        {"ticker": "005930", "name": "삼성전자", "qty": 5,
         "avg_price": 70000, "current_price": 88000,  # 최고가 대비 -12%
         "eval_profit_loss": 0, "profit_loss_rate": 0},
    ]
    triggered = engine.check_trailing_stop()
    assert "005930" in triggered
    engine._client.place_order.assert_called_once()


def test_trailing_stop_does_not_trigger_above_threshold():
    """낙폭이 trailing_stop_pct 이내면 매도하지 않는다."""
    engine = _make_engine()
    engine._peak_prices["005930"] = 100000
    engine._client.get_holdings.return_value = [
        {"ticker": "005930", "name": "삼성전자", "qty": 5,
         "avg_price": 70000, "current_price": 95000,  # 최고가 대비 -5%
         "eval_profit_loss": 0, "profit_loss_rate": 0},
    ]
    triggered = engine.check_trailing_stop()
    assert triggered == []


def test_trailing_stop_cleans_up_sold_ticker():
    """매도 완료 후 해당 종목의 최고가 기록이 삭제된다."""
    engine = _make_engine()
    engine._peak_prices["005930"] = 100000
    engine._client.get_holdings.return_value = [
        {"ticker": "005930", "name": "삼성전자", "qty": 5,
         "avg_price": 70000, "current_price": 85000,  # -15% 트리거
         "eval_profit_loss": 0, "profit_loss_rate": 0},
    ]
    engine.check_trailing_stop()
    assert "005930" not in engine._peak_prices


def test_trailing_stop_skips_excluded_tickers():
    """이미 손절 매도된 종목은 같은 사이클의 트레일링스톱에서 다시 매도하지 않는다."""
    engine = _make_engine()
    engine._peak_prices["005930"] = 100000
    engine._client.get_holdings.return_value = [
        {"ticker": "005930", "name": "삼성전자", "qty": 5,
         "avg_price": 70000, "current_price": 85000,
         "eval_profit_loss": 0, "profit_loss_rate": 0},
    ]

    triggered = engine.check_trailing_stop(exclude_tickers={"005930"})

    assert triggered == []
    engine._client.place_order.assert_not_called()


def test_status_returns_correct_snapshot():
    """status 프로퍼티가 현재 엔진 상태를 올바르게 반환한다."""
    engine = _make_engine(max_buys=5, max_sells=5)
    engine.buy("005930", qty=1)

    s = engine.status
    assert s["daily_buys"] == 1
    assert s["daily_sells"] == 0
    assert s["max_buys"] == 5
    assert s["halted"] is False
