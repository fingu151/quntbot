"""리밸런서 단위 테스트."""
import json
from datetime import date
from unittest.mock import MagicMock

import pytest

from config import PortfolioConfig
from src.trading.rebalancer import RebalanceOrder, compute_rebalance_orders, execute_rebalance


def _portfolio(n: int = 3, enforce_price_filter: bool = True) -> PortfolioConfig:
    return PortfolioConfig(
        initial_capital=10_000_000,
        n_holdings=n,
        enforce_price_filter=enforce_price_filter,
    )


# ------------------------------------------------------------------
# compute_rebalance_orders 테스트
# ------------------------------------------------------------------

def test_sell_tickers_not_in_target():
    """보유 종목이 목표에 없으면 전량 매도 주문이 생성된다."""
    holdings = [
        {"ticker": "005930", "name": "삼성전자", "qty": 5,
         "avg_price": 70000, "current_price": 75000,
         "eval_profit_loss": 0, "profit_loss_rate": 0},
    ]
    target = ["000660"]  # 삼성전자 제외
    prices = {"000660": 100000}

    sells, _ = compute_rebalance_orders(
        holdings=holdings, target_tickers=target,
        prices=prices, cash=1_000_000, portfolio=_portfolio(),
    )

    assert len(sells) == 1
    assert sells[0].ticker == "005930"
    assert sells[0].side == "SELL"
    assert sells[0].qty == 5


def test_buy_tickers_not_held():
    """목표에 있지만 미보유인 종목 매수 주문이 생성된다."""
    holdings = []
    target = ["005930"]
    prices = {"005930": 75000}

    _, buys = compute_rebalance_orders(
        holdings=holdings, target_tickers=target,
        prices=prices, cash=1_000_000, portfolio=_portfolio(n=1),
    )

    assert len(buys) == 1
    assert buys[0].ticker == "005930"
    assert buys[0].side == "BUY"
    assert buys[0].qty == 13  # floor(1_000_000 / 75_000)


def test_held_and_in_target_produces_no_order():
    """이미 보유 중이고 목표에도 있는 종목은 주문을 생성하지 않는다."""
    holdings = [
        {"ticker": "005930", "name": "삼성전자", "qty": 5,
         "avg_price": 70000, "current_price": 75000,
         "eval_profit_loss": 0, "profit_loss_rate": 0},
    ]
    target = ["005930"]
    prices = {"005930": 75000}

    sells, buys = compute_rebalance_orders(
        holdings=holdings, target_tickers=target,
        prices=prices, cash=500_000, portfolio=_portfolio(),
    )

    assert sells == []
    assert buys == []


def test_buy_skipped_when_price_too_high():
    """1주 가격이 배분 금액보다 크면 매수를 건너뛴다."""
    holdings = []
    target = ["005930"]
    prices = {"005930": 500_000}  # 50만원

    _, buys = compute_rebalance_orders(
        holdings=holdings, target_tickers=target,
        prices=prices, cash=100_000,  # 10만원 → 1주도 못 삼
        portfolio=_portfolio(n=1, enforce_price_filter=True),
    )

    assert buys == []


def test_buy_skipped_when_price_missing():
    """prices 딕셔너리에 종목이 없으면 매수를 건너뛴다."""
    _, buys = compute_rebalance_orders(
        holdings=[], target_tickers=["999999"],
        prices={}, cash=1_000_000, portfolio=_portfolio(n=1),
    )
    assert buys == []


def test_buy_skipped_when_execution_price_gap_is_too_large():
    _, buys = compute_rebalance_orders(
        holdings=[],
        target_tickers=["GAPUP", "OK"],
        prices={"GAPUP": 12100, "OK": 11000},
        previous_closes={"GAPUP": 10000, "OK": 10000},
        cash=2_000_000,
        portfolio=_portfolio(n=2),
    )

    assert [order.ticker for order in buys] == ["OK"]


def test_cash_split_evenly_across_buy_targets():
    """예수금이 매수 대상 종목 수로 균등 배분된다."""
    holdings = []
    target = ["A", "B"]
    prices = {"A": 10000, "B": 10000}

    _, buys = compute_rebalance_orders(
        holdings=holdings, target_tickers=target,
        prices=prices, cash=200_000, portfolio=_portfolio(n=2),
    )

    assert len(buys) == 2
    # 200_000 / 2 = 100_000 각각, 100_000 / 10_000 = 10주
    assert all(b.qty == 10 for b in buys)


def test_buy_budget_includes_expected_sell_proceeds():
    """매도 예정 보유 종목의 예상 매도대금을 매수 가능 현금에 반영한다."""
    holdings = [
        {"ticker": "OLD", "name": "기존종목", "qty": 5,
         "avg_price": 8000, "current_price": 10000,
         "eval_profit_loss": 0, "profit_loss_rate": 0},
    ]
    target = ["NEW"]
    prices = {"NEW": 10000}

    sells, buys = compute_rebalance_orders(
        holdings=holdings,
        target_tickers=target,
        prices=prices,
        cash=0,
        portfolio=_portfolio(n=1),
    )

    assert sells == [RebalanceOrder("OLD", "SELL", 5, "rebalance sell buffer exit (holding 5 shares)")]
    assert buys == [RebalanceOrder("NEW", "BUY", 5, "target portfolio entry (budget 50,000 / 10,000 = 5 shares)")]


def test_rank_buffer_keeps_held_ticker_outside_buy_list_but_inside_sell_buffer():
    holdings = [
        {"ticker": "HELD", "name": "Held", "qty": 10, "avg_price": 1000, "current_price": 1000},
    ]

    sells, buys = compute_rebalance_orders(
        holdings=holdings,
        target_tickers=["NEW"],
        prices={"NEW": 1000},
        cash=10_000,
        portfolio=_portfolio(n=1),
        sell_eligible_tickers=[],
    )

    assert sells == []
    assert [order.ticker for order in buys] == ["NEW"]


def test_rank_buffer_sells_held_ticker_outside_sell_buffer():
    holdings = [
        {"ticker": "OLD", "name": "Old", "qty": 10, "avg_price": 1000, "current_price": 1000},
    ]

    sells, _ = compute_rebalance_orders(
        holdings=holdings,
        target_tickers=["NEW"],
        prices={"NEW": 1000},
        cash=10_000,
        portfolio=_portfolio(n=1),
        sell_eligible_tickers=["OLD"],
    )

    assert [order.ticker for order in sells] == ["OLD"]


def test_score_weighted_buy_sizing_uses_target_weights():
    holdings = []
    target = ["AAA", "BBB"]
    prices = {"AAA": 1000, "BBB": 1000}

    _, buys = compute_rebalance_orders(
        holdings=holdings,
        target_tickers=target,
        prices=prices,
        cash=100_000,
        portfolio=_portfolio(n=2),
        target_weights={"AAA": 0.70, "BBB": 0.30},
    )

    assert [(order.ticker, order.qty) for order in buys] == [("AAA", 70), ("BBB", 30)]


def test_buy_budget_multiplier_scales_orders_without_exceeding_budget():
    _, buys = compute_rebalance_orders(
        holdings=[],
        target_tickers=["AAA", "BBB"],
        prices={"AAA": 100, "BBB": 100},
        cash=1_000,
        target_weights={"AAA": 0.60, "BBB": 0.60},
    )

    assert [(order.ticker, order.qty) for order in buys] == [("AAA", 6), ("BBB", 4)]


# ------------------------------------------------------------------
# execute_rebalance 테스트
# ------------------------------------------------------------------

def test_execute_sells_before_buys():
    """매도가 먼저 실행된 뒤 매수가 실행된다."""
    engine = MagicMock()
    engine.sell.return_value = {"rt_cd": "0"}
    engine.buy.return_value = {"rt_cd": "0"}

    sells = [RebalanceOrder("005930", "SELL", 5, "제외")]
    buys = [RebalanceOrder("000660", "BUY", 2, "편입")]

    result = execute_rebalance(engine, sells, buys)

    assert result["sold"] == ["005930"]
    assert result["bought"] == ["000660"]
    assert result["failed"] == []

    # 호출 순서: sell → buy
    sell_call_idx = next(
        i for i, c in enumerate(engine.mock_calls) if "sell" in str(c)
    )
    buy_call_idx = next(
        i for i, c in enumerate(engine.mock_calls) if "buy" in str(c)
    )
    assert sell_call_idx < buy_call_idx


def test_execute_records_failed_on_error():
    """주문 실패 시 failed 목록에 종목코드가 추가된다."""
    engine = MagicMock()
    engine.sell.return_value = {"rt_cd": "1", "msg1": "잔고부족"}

    sells = [RebalanceOrder("005930", "SELL", 5, "제외")]
    result = execute_rebalance(engine, sells, [])

    assert result["failed"] == ["005930"]
    assert result["sold"] == []


def test_execute_records_failed_and_continues_when_sell_raises():
    engine = MagicMock()
    engine.sell.side_effect = [
        {"rt_cd": "0"},
        Exception("500 Server Error"),
        {"rt_cd": "0"},
    ]
    sells = [
        RebalanceOrder("005930", "SELL", 1, "first"),
        RebalanceOrder("000660", "SELL", 1, "second"),
        RebalanceOrder("000270", "SELL", 1, "third"),
    ]

    result = execute_rebalance(engine, sells, [])

    assert result["sold"] == ["005930", "000270"]
    assert result["failed"] == ["000660"]
    assert engine.sell.call_count == 3


def test_execute_skips_buys_when_any_sell_fails():
    engine = MagicMock()
    engine.sell.side_effect = [
        {"rt_cd": "0"},
        Exception("500 Server Error"),
    ]
    engine.buy.return_value = {"rt_cd": "0"}
    sells = [
        RebalanceOrder("005930", "SELL", 1, "first"),
        RebalanceOrder("000660", "SELL", 1, "second"),
    ]
    buys = [RebalanceOrder("000270", "BUY", 1, "entry")]

    result = execute_rebalance(engine, sells, buys)

    assert result["sold"] == ["005930"]
    assert result["failed"] == ["000660"]
    assert result["bought"] == []
    engine.buy.assert_not_called()


def test_execute_records_failed_and_continues_when_buy_raises():
    engine = MagicMock()
    engine.buy.side_effect = [
        {"rt_cd": "0"},
        Exception("500 Server Error"),
        {"rt_cd": "0"},
    ]
    buys = [
        RebalanceOrder("005930", "BUY", 1, "first"),
        RebalanceOrder("000660", "BUY", 1, "second"),
        RebalanceOrder("000270", "BUY", 1, "third"),
    ]

    result = execute_rebalance(engine, [], buys)

    assert result["bought"] == ["005930", "000270"]
    assert result["failed"] == ["000660"]
    assert engine.buy.call_count == 3


def test_execute_rebalance_blocks_orders_when_dry_run_used_fallback_price(tmp_path):
    """dry-run에서 fallback 가격을 쓴 종목이 있으면 주문 실행 전에 차단한다."""
    engine = MagicMock()
    report_path = tmp_path / "dry_run.json"
    report_path.write_text(
        json.dumps({
            "dry_run": True,
            "as_of_date": "2026-05-08",
            "price_fallback_count": 1,
            "price_lookup_failed_count": 0,
            "price_fallbacks": [{"ticker": "000660", "price": 10000, "source": "latest-db"}],
        }),
        encoding="utf-8",
    )

    sells = [RebalanceOrder("005930", "SELL", 5, "exclude")]
    buys = [RebalanceOrder("000660", "BUY", 2, "include")]

    with pytest.raises(RuntimeError, match="fallback"):
        execute_rebalance(engine, sells, buys, preflight_report_path=report_path)

    engine.sell.assert_not_called()
    engine.buy.assert_not_called()


def test_execute_rebalance_blocks_orders_when_dry_run_report_is_stale(tmp_path):
    engine = MagicMock()
    report_path = tmp_path / "dry_run.json"
    report_path.write_text(
        json.dumps({
            "dry_run": True,
            "as_of_date": "2026-05-08",
            "price_fallback_count": 0,
            "price_lookup_failed_count": 0,
            "price_fallbacks": [],
            "price_lookup_failures": [],
        }),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="stale"):
        execute_rebalance(
            engine,
            [],
            [RebalanceOrder("000660", "BUY", 2, "include")],
            preflight_report_path=report_path,
            expected_preflight_date=date(2026, 5, 9),
        )

    engine.sell.assert_not_called()
    engine.buy.assert_not_called()


def test_execute_rebalance_blocks_when_orders_do_not_match_preflight_report(tmp_path):
    engine = MagicMock()
    report_path = tmp_path / "dry_run.json"
    report_path.write_text(
        json.dumps({
            "dry_run": True,
            "as_of_date": "2026-05-08",
            "price_fallback_count": 0,
            "price_lookup_failed_count": 0,
            "orders": [
                {"side": "SELL", "ticker": "005930", "qty": 5, "reason": "exclude"},
                {"side": "BUY", "ticker": "000660", "qty": 2, "reason": "include"},
            ],
        }),
        encoding="utf-8",
    )
    sells = [RebalanceOrder("005930", "SELL", 5, "exclude")]
    buys = [RebalanceOrder("000270", "BUY", 2, "include")]

    with pytest.raises(RuntimeError, match="order mismatch"):
        execute_rebalance(
            engine,
            sells,
            buys,
            preflight_report_path=report_path,
            enforce_preflight_order_match=True,
        )

    engine.sell.assert_not_called()
    engine.buy.assert_not_called()


def test_execute_rebalance_sell_only_order_match_ignores_report_buys(tmp_path):
    engine = MagicMock()
    engine.sell.return_value = {"rt_cd": "0"}
    report_path = tmp_path / "dry_run.json"
    report_path.write_text(
        json.dumps({
            "dry_run": True,
            "as_of_date": "2026-05-08",
            "price_fallback_count": 1,
            "price_lookup_failed_count": 1,
            "price_fallbacks": [{"ticker": "000660", "price": 10000}],
            "price_lookup_failures": ["000270"],
            "orders": [
                {"side": "SELL", "ticker": "005930", "qty": 5, "reason": "exclude"},
                {"side": "BUY", "ticker": "000660", "qty": 2, "reason": "include"},
            ],
        }),
        encoding="utf-8",
    )
    sells = [RebalanceOrder("005930", "SELL", 5, "exclude")]
    buys = []

    result = execute_rebalance(
        engine,
        sells,
        buys,
        preflight_report_path=report_path,
        allow_buys=False,
        enforce_preflight_order_match=True,
    )

    assert result["sold"] == ["005930"]
    engine.buy.assert_not_called()


def test_execute_rebalance_allows_twenty_daily_buys(tmp_path):
    engine = MagicMock()
    engine.buy.return_value = {"rt_cd": "0"}
    report_path = tmp_path / "dry_run.json"
    report_path.write_text(
        json.dumps({
            "dry_run": True,
            "as_of_date": "2026-05-08",
            "buy_count": 20,
            "sell_count": 0,
            "price_fallback_count": 0,
            "price_lookup_failed_count": 0,
            "price_fallbacks": [],
            "price_lookup_failures": [],
        }),
        encoding="utf-8",
    )
    buys = [
        RebalanceOrder(f"{idx:06d}", "BUY", 1, "include")
        for idx in range(20)
    ]

    result = execute_rebalance(
        engine,
        [],
        buys,
        preflight_report_path=report_path,
        expected_preflight_date=date(2026, 5, 8),
    )

    assert len(result["bought"]) == 20
    assert engine.buy.call_count == 20


def test_execute_rebalance_allows_thirty_daily_sells(tmp_path):
    engine = MagicMock()
    engine.sell.return_value = {"rt_cd": "0"}
    report_path = tmp_path / "dry_run.json"
    report_path.write_text(
        json.dumps({
            "dry_run": True,
            "as_of_date": "2026-05-08",
            "buy_count": 0,
            "sell_count": 30,
            "price_fallback_count": 0,
            "price_lookup_failed_count": 0,
            "price_fallbacks": [],
            "price_lookup_failures": [],
        }),
        encoding="utf-8",
    )
    sells = [
        RebalanceOrder(f"{idx:06d}", "SELL", 1, "rebalance exit")
        for idx in range(30)
    ]

    result = execute_rebalance(
        engine,
        sells,
        [],
        preflight_report_path=report_path,
        expected_preflight_date=date(2026, 5, 8),
    )

    assert len(result["sold"]) == 30
    assert engine.sell.call_count == 30


def test_execute_rebalance_blocks_when_dry_run_orders_exceed_daily_sell_limit(tmp_path):
    engine = MagicMock()
    report_path = tmp_path / "dry_run.json"
    report_path.write_text(
        json.dumps({
            "dry_run": True,
            "as_of_date": "2026-05-08",
            "buy_count": 0,
            "sell_count": 31,
            "price_fallback_count": 0,
            "price_lookup_failed_count": 0,
            "price_fallbacks": [],
            "price_lookup_failures": [],
        }),
        encoding="utf-8",
    )
    sells = [
        RebalanceOrder(f"{idx:06d}", "SELL", 1, "rebalance exit")
        for idx in range(31)
    ]

    with pytest.raises(RuntimeError, match="daily sell limit"):
        execute_rebalance(
            engine,
            sells,
            [],
            preflight_report_path=report_path,
            expected_preflight_date=date(2026, 5, 8),
        )

    engine.sell.assert_not_called()


def test_execute_rebalance_blocks_when_dry_run_orders_exceed_daily_buy_limit(tmp_path):
    engine = MagicMock()
    report_path = tmp_path / "dry_run.json"
    report_path.write_text(
        json.dumps({
            "dry_run": True,
            "as_of_date": "2026-05-08",
            "buy_count": 21,
            "sell_count": 0,
            "price_fallback_count": 0,
            "price_lookup_failed_count": 0,
            "price_fallbacks": [],
            "price_lookup_failures": [],
        }),
        encoding="utf-8",
    )
    buys = [
        RebalanceOrder(f"{idx:06d}", "BUY", 1, "include")
        for idx in range(21)
    ]

    with pytest.raises(RuntimeError, match="daily buy limit"):
        execute_rebalance(
            engine,
            [],
            buys,
            preflight_report_path=report_path,
            expected_preflight_date=date(2026, 5, 8),
        )

    engine.buy.assert_not_called()


def test_execute_rebalance_sell_only_ignores_preflight_buy_count(tmp_path):
    engine = MagicMock()
    engine.sell.return_value = {"rt_cd": "0"}
    report_path = tmp_path / "dry_run.json"
    report_path.write_text(
        json.dumps({
            "dry_run": True,
            "as_of_date": "2026-05-08",
            "buy_count": 11,
            "sell_count": 1,
            "price_fallback_count": 0,
            "price_lookup_failed_count": 0,
            "price_fallbacks": [],
            "price_lookup_failures": [],
        }),
        encoding="utf-8",
    )

    result = execute_rebalance(
        engine,
        [RebalanceOrder("005930", "SELL", 1, "risk reduction")],
        [RebalanceOrder("000660", "BUY", 1, "include")],
        preflight_report_path=report_path,
        expected_preflight_date=date(2026, 5, 8),
        allow_buys=False,
    )

    assert result["sold"] == ["005930"]
    assert result["bought"] == []
    engine.sell.assert_called_once()
    engine.buy.assert_not_called()


def test_execute_rebalance_sell_only_ignores_buy_price_preflight_failures(tmp_path):
    engine = MagicMock()
    engine.sell.return_value = {"rt_cd": "0"}
    report_path = tmp_path / "dry_run.json"
    report_path.write_text(
        json.dumps({
            "dry_run": True,
            "as_of_date": "2026-05-08",
            "buy_count": 1,
            "sell_count": 1,
            "price_fallback_count": 1,
            "price_lookup_failed_count": 1,
            "price_fallbacks": [{"ticker": "000660", "price": 10000, "source": "latest-db"}],
            "price_lookup_failures": ["000270"],
        }),
        encoding="utf-8",
    )

    result = execute_rebalance(
        engine,
        [RebalanceOrder("005930", "SELL", 1, "risk reduction")],
        [RebalanceOrder("000660", "BUY", 1, "include")],
        preflight_report_path=report_path,
        expected_preflight_date=date(2026, 5, 8),
        allow_buys=False,
    )

    assert result["sold"] == ["005930"]
    assert result["bought"] == []
    engine.sell.assert_called_once()
    engine.buy.assert_not_called()
