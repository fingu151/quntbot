"""KIS PAPER 인증 + 잔고 조회 + 현재가 조회 스모크 테스트.

실행:
    python scripts/smoke_test_kis.py
"""
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (scripts/ 하위에서 실행해도 import 가능하게)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger

import config
from config import KIS, TRADE_MODE
from src.trading.kis_client import KisClient


def _safe_error_message(exc: Exception) -> str:
    message = str(exc)
    if KIS.account_no:
        message = message.replace(KIS.account_no, f"{KIS.account_no[:4]}****")
    if KIS.app_key:
        message = message.replace(KIS.app_key, "<KIS_APP_KEY>")
    if KIS.app_secret:
        message = message.replace(KIS.app_secret, "<KIS_APP_SECRET>")
    return message


def main() -> None:
    logger.info("=" * 50)
    logger.info("KIS PAPER 스모크 테스트 시작")
    logger.info("=" * 50)

    # 1. 설정 검증
    issues = config.validate()
    if issues:
        for w in issues:
            logger.error(f"설정 오류: {w}")
        sys.exit(1)

    # 2. KIS 키 공백 체크
    missing = []
    if not KIS.app_key:
        missing.append("KIS_APP_KEY")
    if not KIS.app_secret:
        missing.append("KIS_APP_SECRET")
    if not KIS.account_no:
        missing.append("KIS_ACCOUNT_NO")
    if missing:
        logger.error(f".env에 다음 값이 비어 있습니다: {', '.join(missing)}")
        sys.exit(1)

    logger.info(f"TRADE_MODE  : {TRADE_MODE}")
    logger.info(f"BASE_URL    : {KIS.base_url}")
    logger.info(f"ACCOUNT_NO  : {KIS.account_no[:4]}****")  # 앞 4자리만 표시

    # 3. KisClient 초기화
    try:
        client = KisClient()
    except RuntimeError as e:
        logger.error(f"클라이언트 초기화 실패: {e}")
        sys.exit(1)

    # 4. 토큰 발급
    logger.info("-" * 40)
    logger.info("[STEP 1] 토큰 발급")
    try:
        client._ensure_token()
        logger.success("토큰 발급 성공")
    except Exception as e:
        logger.error(f"토큰 발급 실패: {_safe_error_message(e)}")
        sys.exit(1)

    # 5. 잔고 조회
    logger.info("-" * 40)
    logger.info("[STEP 2] 계좌 잔고 조회")
    try:
        balance = client.get_balance()
        rt_cd = balance.get("rt_cd")
        msg = balance.get("msg1", "")

        if rt_cd != "0":
            logger.error(f"잔고 조회 실패: rt_cd={rt_cd!r}, msg={msg!r}")
            sys.exit(1)

        logger.success(f"잔고 조회 성공: {msg}")

        output2 = balance.get("output2") or []
        if output2:
            row = output2[0]
            total = row.get("tot_evlu_amt", "N/A")
            cash = row.get("dnca_tot_amt", "N/A")
            logger.info(f"  총평가금액 : {int(total):,}원" if total != "N/A" else "  총평가금액 : N/A")
            logger.info(f"  예수금     : {int(cash):,}원" if cash != "N/A" else "  예수금     : N/A")
    except Exception as e:
        logger.error(f"잔고 조회 중 예외 발생: {_safe_error_message(e)}")
        sys.exit(1)

    # 6. 현재가 조회 (삼성전자)
    logger.info("-" * 40)
    logger.info("[STEP 3] 현재가 조회 (삼성전자 005930)")
    try:
        price_data = client.get_current_price("005930")
        rt_cd2 = price_data.get("rt_cd")
        msg2 = price_data.get("msg1", "")

        if rt_cd2 != "0":
            logger.error(f"현재가 조회 실패: rt_cd={rt_cd2!r}, msg={msg2!r}")
            sys.exit(1)

        output = price_data.get("output") or {}
        price = output.get("stck_prpr", "N/A")
        name = output.get("hts_kor_isnm", "N/A")
        logger.success(f"현재가 조회 성공: {msg2}")
        logger.info(f"  종목명   : {name}")
        logger.info(f"  현재가   : {int(price):,}원" if price != "N/A" else "  현재가   : N/A")
    except Exception as e:
        logger.error(f"현재가 조회 중 예외 발생: {_safe_error_message(e)}")
        sys.exit(1)

    # 7. 최종 결과
    logger.info("=" * 50)
    logger.success("SMOKE TEST PASSED")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
