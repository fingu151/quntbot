from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import scripts.smoke_test_order as smoke_test_order


KST = ZoneInfo("Asia/Seoul")


def _successful_client() -> MagicMock:
    client = MagicMock()
    client.get_balance.return_value = {
        "rt_cd": "0",
        "output2": [{"dnca_tot_amt": "100000000"}],
    }
    client.place_order.return_value = {
        "rt_cd": "0",
        "output": {"ODNO": "0000001"},
    }
    return client


def test_main_blocks_order_outside_regular_market_hours_without_force():
    client = _successful_client()
    after_close = datetime(2026, 5, 4, 16, 0, tzinfo=KST)

    with patch.object(smoke_test_order, "KisClient", return_value=client):
        result = smoke_test_order.main(argv=[], now=after_close)

    assert result == 1
    client.get_balance.assert_not_called()
    client.place_order.assert_not_called()


def test_main_allows_order_outside_regular_market_hours_with_force():
    client = _successful_client()
    after_close = datetime(2026, 5, 4, 16, 0, tzinfo=KST)

    with patch.object(smoke_test_order, "KisClient", return_value=client):
        result = smoke_test_order.main(argv=["--force"], now=after_close)

    assert result == 0
    assert client.place_order.call_count == 2


def test_main_allows_order_during_regular_market_hours():
    client = _successful_client()
    market_open = datetime(2026, 5, 4, 10, 0, tzinfo=KST)

    with patch.object(smoke_test_order, "KisClient", return_value=client):
        result = smoke_test_order.main(argv=[], now=market_open)

    assert result == 0
    assert client.place_order.call_count == 2
