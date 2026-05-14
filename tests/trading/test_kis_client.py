"""KisClient 단위 테스트 — 실제 HTTP 호출 없이 mock으로 검증."""
import hashlib
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config import KISConfig
from src.trading.kis_client import KisClient


# ------------------------------------------------------------------
# 헬퍼
# ------------------------------------------------------------------

def _make_config() -> KISConfig:
    return KISConfig(
        app_key="test_key",
        app_secret="test_secret",
        account_no="12345678",
        account_product_code="01",
        paper_base_url="https://openapivts.koreainvestment.com:29443",
        live_base_url="https://openapi.koreainvestment.com:9443",
    )


def _make_config_with_cache(path: Path) -> KISConfig:
    return KISConfig(
        app_key="test_key",
        app_secret="test_secret",
        account_no="12345678",
        account_product_code="01",
        paper_base_url="https://openapivts.koreainvestment.com:29443",
        live_base_url="https://openapi.koreainvestment.com:9443",
        token_cache_path=path,
    )


def _app_key_fingerprint(app_key: str = "test_key") -> str:
    return hashlib.sha256(app_key.encode("utf-8")).hexdigest()


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.raise_for_status = MagicMock()
    return mock


@pytest.fixture
def client() -> KisClient:
    with patch("src.trading.kis_client.TRADE_MODE", "PAPER"):
        return KisClient(_make_config())


# ------------------------------------------------------------------
# 테스트
# ------------------------------------------------------------------

def test_live_mode_raises_on_init():
    """LIVE 모드에서 KisClient 생성 시 RuntimeError 발생."""
    with patch("src.trading.kis_client.TRADE_MODE", "LIVE"):
        with pytest.raises(RuntimeError, match="PAPER"):
            KisClient(_make_config())


def test_fetch_token_stores_access_token(client: KisClient):
    """토큰 발급 응답에서 access_token을 인스턴스에 저장한다."""
    token_resp = {
        "access_token": "mock_token_abc",
        "token_type": "Bearer",
        "expires_in": 86400,
    }
    with patch.object(client._session, "post", return_value=_mock_response(token_resp)):
        token = client._fetch_token()

    assert token == "mock_token_abc"
    assert client._access_token == "mock_token_abc"
    assert client._token_expires_at > 0


def test_fetch_token_writes_token_cache(tmp_path: Path):
    cache_path = tmp_path / "kis_token.json"
    with patch("src.trading.kis_client.TRADE_MODE", "PAPER"):
        client = KisClient(_make_config_with_cache(cache_path))

    token_resp = {
        "access_token": "mock_token_abc",
        "token_type": "Bearer",
        "expires_in": 86400,
    }
    with patch.object(client._session, "post", return_value=_mock_response(token_resp)):
        client._fetch_token()

    cached = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cached["access_token"] == "mock_token_abc"
    assert cached["expires_at"] > time.time()
    assert cached["base_url"] == "https://openapivts.koreainvestment.com:29443"
    assert cached["app_key_fingerprint"] == _app_key_fingerprint()
    assert "app_key" not in cached


def test_fetch_token_uses_configured_request_timeout():
    config = KISConfig(
        app_key="test_key",
        app_secret="test_secret",
        account_no="12345678",
        account_product_code="01",
        paper_base_url="https://openapivts.koreainvestment.com:29443",
        live_base_url="https://openapi.koreainvestment.com:9443",
        request_timeout_sec=30,
    )
    with patch("src.trading.kis_client.TRADE_MODE", "PAPER"):
        client = KisClient(config)

    token_resp = {
        "access_token": "mock_token_abc",
        "token_type": "Bearer",
        "expires_in": 86400,
    }
    with patch.object(client._session, "post", return_value=_mock_response(token_resp)) as mock_post:
        client._fetch_token()

    assert mock_post.call_args.kwargs["timeout"] == 30


def test_ensure_token_reuses_cached_token(client: KisClient):
    """만료되지 않은 토큰은 재발급 없이 재사용한다."""
    client._access_token = "cached_token"
    client._token_expires_at = float("inf")

    with patch.object(client._session, "post") as mock_post:
        token = client._ensure_token()

    assert token == "cached_token"
    mock_post.assert_not_called()


def test_ensure_token_reuses_file_cached_token(tmp_path: Path):
    cache_path = tmp_path / "kis_token.json"
    cache_path.write_text(
        json.dumps({
            "access_token": "file_cached_token",
            "expires_at": time.time() + 3600,
            "base_url": "https://openapivts.koreainvestment.com:29443",
            "app_key_fingerprint": _app_key_fingerprint(),
        }),
        encoding="utf-8",
    )
    with patch("src.trading.kis_client.TRADE_MODE", "PAPER"):
        client = KisClient(_make_config_with_cache(cache_path))

    with patch.object(client._session, "post") as mock_post:
        token = client._ensure_token()

    assert token == "file_cached_token"
    assert client._access_token == "file_cached_token"
    mock_post.assert_not_called()


def test_ensure_token_ignores_expired_file_cached_token(tmp_path: Path):
    cache_path = tmp_path / "kis_token.json"
    cache_path.write_text(
        json.dumps({
            "access_token": "expired_token",
            "expires_at": time.time() - 1,
            "base_url": "https://openapivts.koreainvestment.com:29443",
            "app_key_fingerprint": _app_key_fingerprint(),
        }),
        encoding="utf-8",
    )
    with patch("src.trading.kis_client.TRADE_MODE", "PAPER"):
        client = KisClient(_make_config_with_cache(cache_path))

    token_resp = {
        "access_token": "fresh_token",
        "token_type": "Bearer",
        "expires_in": 86400,
    }
    with patch.object(client._session, "post", return_value=_mock_response(token_resp)) as mock_post:
        token = client._ensure_token()

    assert token == "fresh_token"
    assert mock_post.called


def test_ensure_token_ignores_cache_for_different_base_url(tmp_path: Path):
    cache_path = tmp_path / "kis_token.json"
    cache_path.write_text(
        json.dumps({
            "access_token": "wrong_env_token",
            "expires_at": time.time() + 3600,
            "base_url": "https://openapi.koreainvestment.com:9443",
            "app_key_fingerprint": _app_key_fingerprint(),
        }),
        encoding="utf-8",
    )
    with patch("src.trading.kis_client.TRADE_MODE", "PAPER"):
        client = KisClient(_make_config_with_cache(cache_path))

    token_resp = {
        "access_token": "fresh_token",
        "token_type": "Bearer",
        "expires_in": 86400,
    }
    with patch.object(client._session, "post", return_value=_mock_response(token_resp)) as mock_post:
        token = client._ensure_token()

    assert token == "fresh_token"
    assert mock_post.called


def test_get_balance_uses_paper_tr_id(client: KisClient):
    """잔고 조회 시 모의투자 전용 tr_id(VTTC8434R)를 사용한다."""
    client._access_token = "mock_token"
    client._token_expires_at = float("inf")

    balance_resp = {"rt_cd": "0", "msg1": "정상처리", "output1": [], "output2": []}
    with patch.object(client._session, "get", return_value=_mock_response(balance_resp)) as mock_get:
        result = client.get_balance()

    headers_used = mock_get.call_args.kwargs["headers"]
    assert headers_used["tr_id"] == "VTTC8434R"
    assert result["rt_cd"] == "0"


def test_get_balance_sends_account_number(client: KisClient):
    """잔고 조회 시 계좌번호가 쿼리 파라미터에 포함된다."""
    client._access_token = "mock_token"
    client._token_expires_at = float("inf")

    with patch.object(client._session, "get", return_value=_mock_response({"rt_cd": "0"})) as mock_get:
        client.get_balance()

    params_used = mock_get.call_args.kwargs["params"]
    assert params_used["CANO"] == "12345678"


def test_get_current_price_sends_ticker(client: KisClient):
    """현재가 조회 시 종목코드가 쿼리 파라미터에 포함된다."""
    client._access_token = "mock_token"
    client._token_expires_at = float("inf")

    price_resp = {"rt_cd": "0", "output": {"stck_prpr": "75000", "hts_kor_isnm": "삼성전자"}}
    with patch.object(client._session, "get", return_value=_mock_response(price_resp)) as mock_get:
        result = client.get_current_price("005930")

    params_used = mock_get.call_args.kwargs["params"]
    assert params_used["FID_INPUT_ISCD"] == "005930"
    assert result["output"]["stck_prpr"] == "75000"


def test_get_current_price_uses_configured_quote_base_url():
    config = KISConfig(
        app_key="test_key",
        app_secret="test_secret",
        account_no="12345678",
        account_product_code="01",
        paper_base_url="https://paper.example.com",
        live_base_url="https://live.example.com",
        quote_base_url="https://quote.example.com",
    )
    client = KisClient(config)
    client._access_token = "mock_token"
    client._token_expires_at = float("inf")

    with patch.object(client._session, "get", return_value=_mock_response({"rt_cd": "0"})) as mock_get:
        client.get_current_price("005930")

    assert mock_get.call_args.args[0].startswith("https://quote.example.com/")


# ------------------------------------------------------------------
# 주문 테스트
# ------------------------------------------------------------------

def test_place_order_buy_uses_correct_tr_id(client: KisClient):
    """매수 주문 시 모의투자 매수 tr_id(VTTC0802U)를 사용한다."""
    client._access_token = "mock_token"
    client._token_expires_at = float("inf")

    hashkey_resp = {"HASH": "mock_hash_value"}
    order_resp = {"rt_cd": "0", "msg1": "주문접수", "output": {"ODNO": "0000001"}}

    with patch.object(client._session, "post", side_effect=[
        _mock_response(hashkey_resp),   # 1번째 post: hashkey 요청
        _mock_response(order_resp),     # 2번째 post: 실제 주문
    ]) as mock_post:
        result = client.place_order("005930", qty=1, price=0, side="BUY")

    order_call_headers = mock_post.call_args_list[1].kwargs["headers"]
    assert order_call_headers["tr_id"] == "VTTC0802U"
    assert result["rt_cd"] == "0"


def test_place_order_sell_uses_correct_tr_id(client: KisClient):
    """매도 주문 시 모의투자 매도 tr_id(VTTC0801U)를 사용한다."""
    client._access_token = "mock_token"
    client._token_expires_at = float("inf")

    hashkey_resp = {"HASH": "mock_hash_value"}
    order_resp = {"rt_cd": "0", "msg1": "주문접수", "output": {"ODNO": "0000002"}}

    with patch.object(client._session, "post", side_effect=[
        _mock_response(hashkey_resp),
        _mock_response(order_resp),
    ]) as mock_post:
        result = client.place_order("005930", qty=1, price=0, side="SELL")

    order_call_headers = mock_post.call_args_list[1].kwargs["headers"]
    assert order_call_headers["tr_id"] == "VTTC0801U"
    assert result["rt_cd"] == "0"


def test_place_order_market_sets_ord_dvsn_01(client: KisClient):
    """price=0 이면 시장가 주문(ORD_DVSN=01)으로 body가 구성된다."""
    client._access_token = "mock_token"
    client._token_expires_at = float("inf")

    with patch.object(client._session, "post", side_effect=[
        _mock_response({"HASH": "h"}),
        _mock_response({"rt_cd": "0"}),
    ]) as mock_post:
        client.place_order("005930", qty=1, price=0, side="BUY")

    order_body = mock_post.call_args_list[1].kwargs["json"]
    assert order_body["ORD_DVSN"] == "01"
    assert order_body["ORD_UNPR"] == "0"


def test_place_order_limit_sets_ord_dvsn_00(client: KisClient):
    """price > 0 이면 지정가 주문(ORD_DVSN=00)으로 body가 구성된다."""
    client._access_token = "mock_token"
    client._token_expires_at = float("inf")

    with patch.object(client._session, "post", side_effect=[
        _mock_response({"HASH": "h"}),
        _mock_response({"rt_cd": "0"}),
    ]) as mock_post:
        client.place_order("005930", qty=1, price=70000, side="BUY")

    order_body = mock_post.call_args_list[1].kwargs["json"]
    assert order_body["ORD_DVSN"] == "00"
    assert order_body["ORD_UNPR"] == "70000"


def test_place_order_invalid_side_raises(client: KisClient):
    """side가 BUY/SELL 이외 값이면 ValueError 발생."""
    with pytest.raises(ValueError, match="side"):
        client.place_order("005930", qty=1, price=0, side="HOLD")


def test_place_order_zero_qty_raises(client: KisClient):
    """qty가 0 이하면 ValueError 발생."""
    with pytest.raises(ValueError, match="qty"):
        client.place_order("005930", qty=0, price=0, side="BUY")


# ------------------------------------------------------------------
# 보유 종목 / 미체결 / 취소 테스트
# ------------------------------------------------------------------

def test_get_holdings_filters_zero_qty(client: KisClient):
    """보유 수량이 0인 종목은 결과에서 제외된다."""
    client._access_token = "mock_token"
    client._token_expires_at = float("inf")

    balance_resp = {
        "rt_cd": "0",
        "output1": [
            {"pdno": "005930", "prdt_name": "삼성전자", "hldg_qty": "5",
             "pchs_avg_pric": "70000", "prpr": "75000",
             "evlu_pfls_amt": "25000", "evlu_pfls_rt": "7.14"},
            {"pdno": "000660", "prdt_name": "SK하이닉스", "hldg_qty": "0",
             "pchs_avg_pric": "0", "prpr": "0",
             "evlu_pfls_amt": "0", "evlu_pfls_rt": "0"},
        ],
        "output2": [{}],
    }
    with patch.object(client._session, "get", return_value=_mock_response(balance_resp)):
        holdings = client.get_holdings()

    assert len(holdings) == 1
    assert holdings[0]["ticker"] == "005930"
    assert holdings[0]["qty"] == 5
    assert holdings[0]["avg_price"] == 70000


def test_get_holdings_accepts_decimal_numeric_strings(client: KisClient):
    client._access_token = "mock_token"
    client._token_expires_at = float("inf")

    balance_resp = {
        "rt_cd": "0",
        "output1": [
            {"pdno": "005930", "prdt_name": "삼성전자", "hldg_qty": "5.0000",
             "pchs_avg_pric": "168027.5860", "prpr": "170100.0000",
             "evlu_pfls_amt": "10362.0700", "evlu_pfls_rt": "1.23"},
        ],
        "output2": [{}],
    }
    with patch.object(client._session, "get", return_value=_mock_response(balance_resp)):
        holdings = client.get_holdings()

    assert holdings[0]["qty"] == 5
    assert holdings[0]["avg_price"] == 168027
    assert holdings[0]["current_price"] == 170100
    assert holdings[0]["eval_profit_loss"] == 10362


def test_get_holdings_empty_when_no_positions(client: KisClient):
    """보유 종목이 없으면 빈 리스트를 반환한다."""
    client._access_token = "mock_token"
    client._token_expires_at = float("inf")

    balance_resp = {"rt_cd": "0", "output1": [], "output2": [{}]}
    with patch.object(client._session, "get", return_value=_mock_response(balance_resp)):
        holdings = client.get_holdings()

    assert holdings == []


def test_get_pending_orders_parses_side(client: KisClient):
    """미체결 조회 시 sll_buy_dvsn_cd 02=BUY, 01=SELL 로 변환된다."""
    client._access_token = "mock_token"
    client._token_expires_at = float("inf")

    pending_resp = {
        "rt_cd": "0",
        "output": [
            {"odno": "0000001", "pdno": "005930", "prdt_name": "삼성전자",
             "sll_buy_dvsn_cd": "02", "ord_qty": "1", "ord_unpr": "0",
             "tot_ccld_qty": "0"},
            {"odno": "0000002", "pdno": "000660", "prdt_name": "SK하이닉스",
             "sll_buy_dvsn_cd": "01", "ord_qty": "2", "ord_unpr": "150000",
             "tot_ccld_qty": "0"},
        ],
    }
    with patch.object(client._session, "get", return_value=_mock_response(pending_resp)):
        orders = client.get_pending_orders()

    assert len(orders) == 2
    assert orders[0]["side"] == "BUY"
    assert orders[1]["side"] == "SELL"
    assert orders[0]["order_no"] == "0000001"


def test_cancel_order_uses_correct_tr_id(client: KisClient):
    """주문 취소 시 tr_id VTTC0803U 를 사용한다."""
    client._access_token = "mock_token"
    client._token_expires_at = float("inf")

    with patch.object(client._session, "post", side_effect=[
        _mock_response({"HASH": "h"}),
        _mock_response({"rt_cd": "0", "msg1": "취소접수"}),
    ]) as mock_post:
        result = client.cancel_order("0000001", "005930", qty=1)

    headers_used = mock_post.call_args_list[1].kwargs["headers"]
    assert headers_used["tr_id"] == "VTTC0803U"
    assert result["rt_cd"] == "0"
