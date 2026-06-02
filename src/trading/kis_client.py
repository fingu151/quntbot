"""KIS (한국투자증권) 모의투자 API 클라이언트 — PAPER 모드 전용."""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

import requests
from loguru import logger

from config import KIS, KISConfig, TRADE_MODE


def _parse_int_number(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(float(value))


class KisClient:
    """KIS 모의투자 API 클라이언트.

    PAPER 모드에서만 초기화 가능. LIVE 모드에서 생성하면 RuntimeError.
    """

    def __init__(self, config: KISConfig = KIS) -> None:
        if TRADE_MODE != "PAPER":
            raise RuntimeError(
                f"KisClient는 PAPER 모드에서만 사용 가능합니다. "
                f"현재 TRADE_MODE={TRADE_MODE!r}"
            )
        self._config = config
        self._access_token: str = ""
        self._token_expires_at: float = 0.0
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # 인증
    # ------------------------------------------------------------------

    def _fetch_token(self) -> str:
        """KIS 서버에서 접근 토큰을 새로 발급받아 인스턴스에 캐시한다."""
        url = f"{self._config.base_url}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": self._config.app_key,
            "appsecret": self._config.app_secret,
        }
        resp = self._session.post(url, json=body, timeout=self._config.request_timeout_sec)
        resp.raise_for_status()
        data = resp.json()

        self._access_token = data["access_token"]
        expires_in = int(data.get("expires_in", 86400))
        # 10초 여유를 두고 만료 처리
        self._token_expires_at = time.time() + expires_in - 10
        self._write_token_cache()

        logger.info(f"KIS 토큰 발급 완료 (유효 {expires_in}초)")
        return self._access_token

    def _ensure_token(self) -> str:
        """토큰이 없거나 만료됐으면 재발급, 아니면 캐시된 토큰 반환."""
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token
        cached = self._read_token_cache()
        if cached:
            return cached
        return self._fetch_token()

    def _read_token_cache(self) -> str:
        path = self._config.token_cache_path
        if not path.exists():
            return ""
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ""
        token = str(cached.get("access_token", ""))
        expires_at = float(cached.get("expires_at", 0) or 0)
        if cached.get("base_url") != self._config.base_url:
            return ""
        if cached.get("app_key_fingerprint") != self._app_key_fingerprint():
            return ""
        if not token or time.time() >= expires_at:
            return ""
        self._access_token = token
        self._token_expires_at = expires_at
        return token

    def _write_token_cache(self) -> None:
        path = self._config.token_cache_path
        payload = {
            "access_token": self._access_token,
            "expires_at": self._token_expires_at,
            "base_url": self._config.base_url,
            "app_key_fingerprint": self._app_key_fingerprint(),
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload), encoding="utf-8")
        except OSError as exc:
            logger.warning(f"KIS token cache write failed: {exc}")

    def _app_key_fingerprint(self) -> str:
        return hashlib.sha256(self._config.app_key.encode("utf-8")).hexdigest()

    def _headers(self, tr_id: str) -> dict[str, str]:
        token = self._ensure_token()
        return {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self._config.app_key,
            "appsecret": self._config.app_secret,
            "tr_id": tr_id,
            "custtype": "P",  # P=개인, B=법인
        }

    # ------------------------------------------------------------------
    # 조회 API
    # ------------------------------------------------------------------

    def get_balance(self) -> dict[str, Any]:
        """모의투자 계좌 잔고 조회 (tr_id: VTTC8434R)."""
        url = f"{self._config.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        params = {
            "CANO": self._config.account_no,
            "ACNT_PRDT_CD": self._config.account_product_code,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        merged: dict[str, Any] | None = None
        output1: list[dict[str, Any]] = []

        for page in range(20):
            for attempt in range(3):
                resp = self._session.get(
                    url,
                    headers=self._headers("VTTC8434R"),
                    params=params,
                    timeout=self._config.request_timeout_sec,
                )
                if resp.status_code != 500:
                    break
                try:
                    message = str(resp.json().get("msg1") or "")
                except (TypeError, ValueError):
                    message = ""
                if "초당" not in message or attempt == 2:
                    break
                time.sleep(0.7 * (attempt + 1))
            resp.raise_for_status()
            data = resp.json()
            if merged is None:
                merged = dict(data)
            output1.extend(data.get("output1") or [])
            if data.get("output2"):
                merged["output2"] = data.get("output2")

            next_fk_raw = str(data.get("ctx_area_fk100") or "")
            next_nk_raw = str(data.get("ctx_area_nk100") or "")
            if data.get("rt_cd") != "0" or not (next_fk_raw.strip() or next_nk_raw.strip()):
                break
            params["CTX_AREA_FK100"] = next_fk_raw
            params["CTX_AREA_NK100"] = next_nk_raw
            if page < 19:
                time.sleep(0.7)

        result = merged or {}
        result["output1"] = output1
        return result

    def get_holdings(self) -> list[dict[str, Any]]:
        """보유 종목 목록 조회.

        get_balance()의 output1을 파싱해 보유 수량이 있는 종목만 반환한다.

        Returns:
            [{"ticker": "005930", "name": "삼성전자", "qty": 10,
              "avg_price": 70000, "current_price": 75000,
              "eval_profit_loss": 50000, "profit_loss_rate": 7.14}, ...]
        """
        raw = self.get_balance()
        rows = []
        for item in raw.get("output1") or []:
            qty = _parse_int_number(item.get("hldg_qty", 0))
            if qty <= 0:
                continue
            rows.append({
                "ticker":            item.get("pdno", ""),
                "name":              item.get("prdt_name", ""),
                "qty":               qty,
                "avg_price":         _parse_int_number(item.get("pchs_avg_pric", 0)),
                "current_price":     _parse_int_number(item.get("prpr", 0)),
                "eval_profit_loss":  _parse_int_number(item.get("evlu_pfls_amt", 0)),
                "profit_loss_rate":  float(item.get("evlu_pfls_rt", 0) or 0),
            })
        return rows

    def get_pending_orders(self) -> list[dict[str, Any]]:
        """미체결 주문 목록 조회 (tr_id: VTTC8036R).

        Returns:
            [{"order_no": "0000001", "ticker": "005930", "name": "삼성전자",
              "side": "BUY", "qty": 1, "price": 0, "filled_qty": 0}, ...]
        """
        url = f"{self._config.base_url}/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl"
        params = {
            "CANO":          self._config.account_no,
            "ACNT_PRDT_CD":  self._config.account_product_code,
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
            "INQR_DVSN_1":  "0",
            "INQR_DVSN_2":  "0",
        }
        resp = self._session.get(
            url,
            headers=self._headers("VTTC8036R"),
            params=params,
            timeout=self._config.request_timeout_sec,
        )
        resp.raise_for_status()
        raw = resp.json()

        rows = []
        for item in raw.get("output") or []:
            side_code = item.get("sll_buy_dvsn_cd", "")
            rows.append({
                "order_no":   item.get("odno", ""),
                "ticker":     item.get("pdno", ""),
                "name":       item.get("prdt_name", ""),
                "side":       "BUY" if side_code == "02" else "SELL",
                "qty":        int(item.get("ord_qty", 0) or 0),
                "price":      int(item.get("ord_unpr", 0) or 0),
                "filled_qty": int(item.get("tot_ccld_qty", 0) or 0),
            })
        return rows

    def cancel_order(self, order_no: str, ticker: str, qty: int) -> dict[str, Any]:
        """미체결 주문 취소 (tr_id: VTTC0803U).

        Args:
            order_no: 취소할 주문번호 (get_pending_orders의 order_no)
            ticker:   종목코드 6자리
            qty:      취소할 수량 (보통 미체결 잔량 전부)

        Returns:
            KIS 응답 dict. rt_cd=="0" 이면 취소 접수 성공.
        """
        body = {
            "CANO":          self._config.account_no,
            "ACNT_PRDT_CD":  self._config.account_product_code,
            "KCP_DVSN":      "02",   # 02=취소
            "ORGN_ODNO":     order_no,
            "ORD_DVSN":      "00",
            "RVSE_CNCL_DVSN_CD": "02",
            "ORD_QTY":       str(qty),
            "ORD_UNPR":      "0",
            "QTY_ALL_ORD_YN": "Y",
            "PDNO":          ticker,
        }
        hashkey = self._get_hashkey(body)
        url = f"{self._config.base_url}/uapi/domestic-stock/v1/trading/order-rvsecncl"
        resp = self._session.post(
            url,
            json=body,
            headers=self._order_headers("VTTC0803U", hashkey),
            timeout=self._config.request_timeout_sec,
        )
        resp.raise_for_status()
        result = resp.json()
        logger.info(
            f"주문 취소: {ticker} 주문번호={order_no} "
            f"→ rt_cd={result.get('rt_cd')}, msg={result.get('msg1')}"
        )
        return result

    # ------------------------------------------------------------------
    # 주문 API
    # ------------------------------------------------------------------

    def _get_hashkey(self, body: dict[str, Any]) -> str:
        """주문 body를 KIS 서버에 보내 hashkey(위변조 방지 서명)를 받는다.

        KIS POST 주문은 반드시 hashkey를 헤더에 포함해야 한다.
        """
        url = f"{self._config.base_url}/uapi/hashkey"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "appkey": self._config.app_key,
            "appsecret": self._config.app_secret,
        }
        resp = self._session.post(
            url,
            json=body,
            headers=headers,
            timeout=self._config.request_timeout_sec,
        )
        resp.raise_for_status()
        return resp.json()["HASH"]

    def _order_headers(self, tr_id: str, hashkey: str) -> dict[str, str]:
        """주문 전용 헤더 — 기본 헤더에 hashkey를 추가한다."""
        headers = self._headers(tr_id)
        headers["hashkey"] = hashkey
        return headers

    def place_order(
        self,
        ticker: str,
        qty: int,
        price: int,
        side: str,
    ) -> dict[str, Any]:
        """모의투자 주식 주문 (매수/매도).

        Args:
            ticker: 종목코드 6자리 (예: "005930")
            qty:    주문 수량 (1 이상 정수)
            price:  주문 단가. 0이면 시장가 주문.
            side:   "BUY"(매수) 또는 "SELL"(매도)

        Returns:
            KIS 응답 dict. rt_cd=="0" 이면 정상 접수.
        """
        if side not in ("BUY", "SELL"):
            raise ValueError(f"side는 'BUY' 또는 'SELL' 이어야 합니다. 입력값: {side!r}")
        if qty <= 0:
            raise ValueError(f"qty는 1 이상이어야 합니다. 입력값: {qty}")

        # 모의투자 tr_id: VTTC0802U=매수, VTTC0801U=매도
        tr_id = "VTTC0802U" if side == "BUY" else "VTTC0801U"

        # 주문구분: 00=지정가, 01=시장가
        ord_dvsn = "01" if price == 0 else "00"

        body = {
            "CANO": self._config.account_no,
            "ACNT_PRDT_CD": self._config.account_product_code,
            "PDNO": ticker,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price),
        }

        hashkey = self._get_hashkey(body)
        url = f"{self._config.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        resp = self._session.post(
            url,
            json=body,
            headers=self._order_headers(tr_id, hashkey),
            timeout=self._config.request_timeout_sec,
        )
        resp.raise_for_status()
        result = resp.json()

        action = "매수" if side == "BUY" else "매도"
        order_type = "시장가" if price == 0 else f"지정가 {price:,}원"
        logger.info(
            f"주문 접수: {action} {ticker} {qty}주 {order_type} "
            f"→ rt_cd={result.get('rt_cd')}, msg={result.get('msg1')}"
        )
        return result

    def get_current_price(self, ticker: str) -> dict[str, Any]:
        """특정 종목 현재가 조회 (tr_id: FHKST01010100).

        시장 데이터 조회는 모의투자 서버(openapivts)가 지원하지 않아
        실서버(openapi) URL을 사용한다. 읽기 전용이므로 실전 주문 위험 없음.

        Args:
            ticker: 종목코드 6자리 (예: "005930" = 삼성전자)
        """
        url = f"{self._config.quote_base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",  # J=주식
            "FID_INPUT_ISCD": ticker,
        }
        resp = self._session.get(
            url,
            headers=self._headers("FHKST01010100"),
            params=params,
            timeout=self._config.request_timeout_sec,
        )
        resp.raise_for_status()
        return resp.json()
