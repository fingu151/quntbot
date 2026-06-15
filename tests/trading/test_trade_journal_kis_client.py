from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from src.trading.kis_client import KisClient
from tests.trading.test_kis_client import _make_config, _mock_response


def test_get_daily_filled_orders_parses_filled_buy_and_sell_rows() -> None:
    client = KisClient(_make_config())
    client._access_token = "mock_token"
    client._token_expires_at = float("inf")
    response = {
        "rt_cd": "0",
        "ctx_area_fk100": "",
        "ctx_area_nk100": "",
        "output1": [
            {
                "odno": "0000001",
                "pdno": "005930",
                "prdt_name": "Samsung",
                "sll_buy_dvsn_cd": "02",
                "ord_qty": "3",
                "tot_ccld_qty": "2",
                "avg_prvs": "70000.5000",
                "tot_ccld_amt": "140001",
                "ord_dt": "20260508",
                "ord_tmd": "093001",
            },
            {
                "odno": "0000002",
                "pdno": "000660",
                "prdt_name": "Hynix",
                "sll_buy_dvsn_cd": "01",
                "ord_qty": "1",
                "tot_ccld_qty": "1",
                "avg_prvs": "150000",
                "ord_dt": "20260508",
                "ord_tmd": "100001",
            },
            {
                "odno": "0000003",
                "pdno": "035420",
                "prdt_name": "NAVER",
                "sll_buy_dvsn_cd": "02",
                "ord_qty": "1",
                "tot_ccld_qty": "0",
                "avg_prvs": "0",
                "ord_dt": "20260508",
                "ord_tmd": "100101",
            },
        ],
    }

    with patch.object(client._session, "get", return_value=_mock_response(response)) as mock_get:
        rows = client.get_daily_filled_orders(
            date(2026, 5, 8),
            date(2026, 5, 8),
            order_nos={"0000001", "0000002"},
        )

    assert [row.order_no for row in rows] == ["0000001", "0000002"]
    assert rows[0].side == "BUY"
    assert rows[0].filled_qty == 2
    assert rows[0].avg_fill_price == 70000.5
    assert rows[0].filled_amount == 140001.0
    assert rows[0].filled_at.isoformat() == "2026-05-08T09:30:01"
    assert rows[1].side == "SELL"
    assert rows[1].filled_amount == 150000.0
    assert mock_get.call_args.kwargs["headers"]["tr_id"] == "VTTC8001R"
    assert mock_get.call_args.kwargs["params"]["INQR_STRT_DT"] == "20260508"


def test_get_daily_filled_orders_masks_sensitive_values_on_error() -> None:
    client = KisClient(_make_config())
    client._access_token = "mock_token"
    client._token_expires_at = float("inf")

    with patch.object(
        client._session,
        "get",
        side_effect=RuntimeError("leaked 12345678 test_key test_secret mock_token"),
    ):
        with pytest.raises(RuntimeError) as exc_info:
            client.get_daily_filled_orders(date(2026, 5, 8), date(2026, 5, 8))

    message = str(exc_info.value)
    assert "12345678" not in message
    assert "test_key" not in message
    assert "test_secret" not in message
    assert "mock_token" not in message
    assert "<KIS_SECRET>" in message
