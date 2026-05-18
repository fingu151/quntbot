"""거래 엔진 — 안전장치 + KisClient 래퍼."""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from typing import Any

from loguru import logger

from config import DATA_DIR, EXIT_RULES, SAFETY, ExitRulesConfig, SafetyConfig
from src.notify.notifier import TelegramNotifier
from src.trading.exit_state import ExitStateStore
from src.trading.kis_client import KisClient


class TradingEngine:
    """안전장치를 포함한 모의투자 거래 엔진.

    KisClient를 직접 쓰지 않고 이 클래스를 통해 주문을 낸다.
    매일 첫 사용 시 카운터가 자동 초기화된다.
    """

    def __init__(
        self,
        client: KisClient,
        safety: SafetyConfig = SAFETY,
        exit_rules: ExitRulesConfig = EXIT_RULES,
        notifier: TelegramNotifier | None = None,
        daily_anchor_path: Path | None = None,
        exit_state_path: Path | None = None,
    ) -> None:
        self._client = client
        self._safety = safety
        self._exit_rules = exit_rules
        self._notifier = notifier or TelegramNotifier()

        self._today: date = date.today()
        self._daily_buys: int = 0
        self._daily_sells: int = 0
        self._halted: bool = False   # 일일 손실 한도 초과 시 True
        self._daily_start_equity: int | None = None
        self._daily_anchor_path = daily_anchor_path or (DATA_DIR / "daily_anchor.json")
        self._exit_state_store = ExitStateStore(
            exit_state_path or (DATA_DIR / "exit_state.json")
        )
        self._peak_prices: dict[str, float] = {}  # {ticker: 보유 후 최고가}

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _reset_if_new_day(self) -> None:
        """날짜가 바뀌면 일일 카운터를 초기화한다."""
        today = date.today()
        if today != self._today:
            self._today = today
            self._daily_buys = 0
            self._daily_sells = 0
            self._halted = False
            self._daily_start_equity = None
            logger.info("일일 카운터 초기화 (새 날짜)")

    def _check_halted(self) -> None:
        if self._halted:
            raise RuntimeError("일일 손실 한도 초과로 당일 매매가 중단되었습니다.")

    # ------------------------------------------------------------------
    # 공개 주문 인터페이스
    # ------------------------------------------------------------------

    def _load_daily_start_equity(self) -> int | None:
        try:
            raw = json.loads(self._daily_anchor_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(f"daily anchor load failed: {exc}")
            return None

        if raw.get("date") != self._today.isoformat():
            return None
        try:
            equity = int(raw.get("start_equity"))
        except (TypeError, ValueError):
            return None
        return equity if equity > 0 else None

    def _save_daily_start_equity(self, equity: int) -> None:
        payload = {"date": self._today.isoformat(), "start_equity": int(equity)}
        try:
            self._daily_anchor_path.parent.mkdir(parents=True, exist_ok=True)
            self._daily_anchor_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning(f"daily anchor save failed: {exc}")

    def buy(self, ticker: str, qty: int, price: int = 0, name: str = "") -> dict[str, Any]:
        """매수 주문. 일일 매수 한도 초과 시 RuntimeError.

        Args:
            ticker: 종목코드 6자리
            qty:    매수 수량
            price:  지정가 단가. 0이면 시장가.
            name:   종목명 (알림용). 없으면 ticker로 표시.
        """
        self._reset_if_new_day()
        self._check_halted()

        if self._daily_buys >= self._safety.max_daily_buys:
            raise RuntimeError(
                f"일일 매수 한도 초과: {self._daily_buys}/{self._safety.max_daily_buys}"
            )

        result = self._client.place_order(ticker, qty=qty, price=price, side="BUY")
        if result.get("rt_cd") == "0":
            self._daily_buys += 1
            logger.info(f"[엔진] 매수 접수 완료 ({self._daily_buys}/{self._safety.max_daily_buys})")
            order_no = result.get("output", {}).get("ODNO", "")
            self._notifier.notify_order("BUY", ticker, name or ticker, qty, price, order_no)
        return result

    def sell(self, ticker: str, qty: int, price: int = 0, name: str = "") -> dict[str, Any]:
        """매도 주문. 일일 매도 한도 초과 시 RuntimeError.

        Args:
            ticker: 종목코드 6자리
            qty:    매도 수량
            price:  지정가 단가. 0이면 시장가.
            name:   종목명 (알림용). 없으면 ticker로 표시.
        """
        self._reset_if_new_day()
        self._check_halted()

        if self._daily_sells >= self._safety.max_daily_sells:
            raise RuntimeError(
                f"일일 매도 한도 초과: {self._daily_sells}/{self._safety.max_daily_sells}"
            )

        result = self._client.place_order(ticker, qty=qty, price=price, side="SELL")
        if result.get("rt_cd") == "0":
            self._daily_sells += 1
            logger.info(f"[엔진] 매도 접수 완료 ({self._daily_sells}/{self._safety.max_daily_sells})")
            order_no = result.get("output", {}).get("ODNO", "")
            self._notifier.notify_order("SELL", ticker, name or ticker, qty, price, order_no)
        return result

    # ------------------------------------------------------------------
    # 손절 / 트레일링 스톱 감시
    # ------------------------------------------------------------------

    def check_stop_loss(self) -> list[str]:
        """보유 종목을 순회하며 손절 조건을 확인하고 해당 종목을 시장가 매도한다.

        손절 조건:
            현재가 / 평균단가 - 1 <= stop_loss_pct  (예: -8%)

        Returns:
            손절 매도가 실행된 종목코드 리스트
        """
        self._reset_if_new_day()
        self._check_halted()

        triggered = []
        holdings = self._client.get_holdings()

        for h in holdings:
            avg = h["avg_price"]
            current = h["current_price"]
            if avg <= 0 or current <= 0:
                continue

            pnl_rate = (current / avg) - 1.0
            if pnl_rate <= self._exit_rules.stop_loss_pct:
                logger.warning(
                    f"[손절] {h['name']}({h['ticker']}) "
                    f"수익률={pnl_rate:.2%} → 손절 기준 {self._exit_rules.stop_loss_pct:.2%} 도달. "
                    f"시장가 매도 실행."
                )
                self._notifier.notify_stop_loss(
                    h["ticker"], h["name"], h["qty"], pnl_rate
                )
                result = self.sell(h["ticker"], qty=h["qty"], price=0, name=h["name"])
                if result.get("rt_cd") == "0":
                    triggered.append(h["ticker"])

        return triggered

    def check_trailing_stop(self, exclude_tickers: set[str] | None = None) -> list[str]:
        """보유 종목의 최고가를 갱신하고 트레일링 스톱 조건을 확인한다.

        트레일링 스톱 조건:
            현재가 / 보유 후 최고가 - 1 <= trailing_stop_pct  (예: -10%)

        최고가는 self._peak_prices 에 종목별로 메모리 저장된다.
        매도 후에는 해당 종목의 최고가 기록을 삭제한다.

        Returns:
            트레일링 스톱 매도가 실행된 종목코드 리스트
        """
        self._reset_if_new_day()
        self._check_halted()

        triggered = []
        exclude_tickers = exclude_tickers or set()
        holdings = self._client.get_holdings()

        for h in holdings:
            ticker = h["ticker"]
            if ticker in exclude_tickers:
                continue
            current = float(h["current_price"])
            if current <= 0:
                continue

            # 최고가 갱신
            peak = self._peak_prices.get(ticker, current)
            if current > peak:
                peak = current
            self._peak_prices[ticker] = peak

            # 트레일링 스톱 체크
            trail_rate = (current / peak) - 1.0
            if trail_rate <= self._exit_rules.trailing_stop_pct:
                logger.warning(
                    f"[트레일링스톱] {h['name']}({ticker}) "
                    f"최고가={peak:,.0f}원 → 현재={current:,.0f}원 "
                    f"({trail_rate:.2%}), 기준 {self._exit_rules.trailing_stop_pct:.2%}. "
                    f"시장가 매도 실행."
                )
                self._notifier.notify_stop_loss(ticker, h["name"], h["qty"], trail_rate)
                result = self.sell(ticker, qty=h["qty"], price=0, name=h["name"])
                if result.get("rt_cd") == "0":
                    triggered.append(ticker)
                    del self._peak_prices[ticker]

        # 더 이상 보유하지 않는 종목의 최고가 기록 정리
        held = {h["ticker"] for h in holdings}
        for ticker in list(self._peak_prices):
            if ticker not in held:
                del self._peak_prices[ticker]

        return triggered

    def check_exit_rules(self) -> list[str]:
        """Run the staged PAPER exit monitor for current holdings."""
        self._reset_if_new_day()
        self._check_halted()

        triggered: list[str] = []
        holdings = self._client.get_holdings()
        held_tickers = {
            h["ticker"]
            for h in holdings
            if int(h.get("qty", 0) or 0) > 0
        }
        self._exit_state_store.prune(held_tickers)

        processable_holdings = [
            h
            for h in holdings
            if int(h.get("qty", 0) or 0) > 0
            and float(h.get("avg_price", 0) or 0) > 0
            and float(h.get("current_price", 0) or 0) > 0
        ]

        for h in processable_holdings:
            ticker = h["ticker"]
            name = h.get("name", ticker)
            qty = int(h.get("qty", 0) or 0)
            avg = float(h.get("avg_price", 0) or 0)
            current = float(h.get("current_price", 0) or 0)

            state = self._exit_state_store.get_or_create(
                ticker=ticker,
                entry_price=avg,
                qty=qty,
                entry_date=self._today.isoformat(),
            )
            pnl_rate = (current / avg) - 1.0

            if pnl_rate <= self._exit_rules.stop_loss_pct:
                logger.warning(
                    f"[Exit full stop] {name}({ticker}) pnl={pnl_rate:.2%}, "
                    f"threshold={self._exit_rules.stop_loss_pct:.2%}. Selling full position."
                )
                self._notifier.notify_stop_loss(ticker, name, qty, pnl_rate)
                result = self.sell(ticker, qty=qty, price=0, name=name)
                if result.get("rt_cd") == "0":
                    self._exit_state_store.delete(ticker)
                    triggered.append(ticker)
                continue

            if (
                not state.profit_take_done
                and pnl_rate >= self._exit_rules.profit_take_pct
            ):
                sell_qty = math.floor(qty * self._exit_rules.profit_take_sell_fraction)
                if sell_qty <= 0:
                    continue
                logger.warning(
                    f"[Exit profit take] {name}({ticker}) pnl={pnl_rate:.2%}, "
                    f"threshold={self._exit_rules.profit_take_pct:.2%}. Selling {sell_qty}."
                )
                result = self.sell(ticker, qty=sell_qty, price=0, name=name)
                if result.get("rt_cd") == "0":
                    remaining_qty = max(qty - sell_qty, 0)
                    state.profit_take_done = True
                    state.trailing_qty = remaining_qty // 2
                    state.breakeven_qty = remaining_qty - state.trailing_qty
                    state.peak_price = max(state.peak_price, current)
                    self._exit_state_store.save_position(state)
                    triggered.append(ticker)
                continue

            if not state.profit_take_done:
                continue

            if current > state.peak_price:
                state.peak_price = current
                self._exit_state_store.save_position(state)

            if state.trailing_qty > 0 and state.peak_price > 0:
                trail_rate = (current / state.peak_price) - 1.0
                if trail_rate <= self._exit_rules.trailing_stop_pct:
                    logger.warning(
                        f"[Exit trailing bucket] {name}({ticker}) "
                        f"peak={state.peak_price:,.0f}, current={current:,.0f}, "
                        f"drawdown={trail_rate:.2%}. Selling {state.trailing_qty}."
                    )
                    self._notifier.notify_stop_loss(
                        ticker, name, state.trailing_qty, trail_rate
                    )
                    result = self.sell(
                        ticker, qty=state.trailing_qty, price=0, name=name
                    )
                    if result.get("rt_cd") == "0":
                        state.trailing_qty = 0
                        if state.breakeven_qty <= 0:
                            self._exit_state_store.delete(ticker)
                        else:
                            self._exit_state_store.save_position(state)
                        triggered.append(ticker)

            breakeven_price = avg * (1.0 + self._exit_rules.breakeven_stop_pct)
            if state.breakeven_qty > 0 and current <= breakeven_price:
                logger.warning(
                    f"[Exit breakeven bucket] {name}({ticker}) "
                    f"current={current:,.0f}, breakeven={breakeven_price:,.0f}. "
                    f"Selling {state.breakeven_qty}."
                )
                result = self.sell(ticker, qty=state.breakeven_qty, price=0, name=name)
                if result.get("rt_cd") == "0":
                    state.breakeven_qty = 0
                    if state.trailing_qty <= 0:
                        self._exit_state_store.delete(ticker)
                    else:
                        self._exit_state_store.save_position(state)
                    if ticker not in triggered:
                        triggered.append(ticker)

        return triggered

    def check_daily_loss_limit(self) -> bool:
        """당일 계좌 수익률이 손실 한도를 초과했는지 확인한다.

        손실 한도 초과 시 self._halted=True 로 설정해 이후 주문을 모두 차단한다.

        Returns:
            True: 한도 초과(매매 중단), False: 정상
        """
        balance = self._client.get_balance()
        output2 = (balance.get("output2") or [{}])[0]

        total_eval = int(output2.get("tot_evlu_amt", 0) or 0)

        if total_eval <= 0:
            return False

        if self._daily_start_equity is None:
            self._daily_start_equity = self._load_daily_start_equity()

        if self._daily_start_equity is None:
            self._daily_start_equity = total_eval
            self._save_daily_start_equity(total_eval)
            logger.info(f"일일 손실 기준자산 설정: {total_eval:,}원")
            return False

        daily_pnl_rate = (total_eval / self._daily_start_equity) - 1.0
        if daily_pnl_rate <= self._safety.daily_loss_limit_pct:
            logger.error(
                f"[긴급] 일일 손실 한도 초과: {daily_pnl_rate:.2%} "
                f"(한도 {self._safety.daily_loss_limit_pct:.2%}). 당일 매매 중단."
            )
            self._halted = True
            self._notifier.notify_daily_loss_halt(daily_pnl_rate)

        return self._halted

    # ------------------------------------------------------------------
    # 상태 조회
    # ------------------------------------------------------------------

    def get_holdings(self) -> list[dict[str, Any]]:
        return self._client.get_holdings()

    def get_balance(self) -> dict[str, Any]:
        return self._client.get_balance()

    def get_current_price(self, ticker: str) -> dict[str, Any]:
        return self._client.get_current_price(ticker)

    def get_exit_state_entry_dates(self) -> dict[str, date]:
        entry_dates: dict[str, date] = {}
        for ticker, state in self._exit_state_store.load().items():
            try:
                entry_dates[ticker] = date.fromisoformat(state.entry_date)
            except ValueError:
                logger.warning(
                    f"exit state entry date ignored: ticker={ticker}, "
                    f"entry_date={state.entry_date}"
                )
        return entry_dates

    @property
    def status(self) -> dict[str, Any]:
        """현재 엔진 상태 스냅샷."""
        return {
            "date":         str(self._today),
            "daily_buys":   self._daily_buys,
            "daily_sells":  self._daily_sells,
            "max_buys":     self._safety.max_daily_buys,
            "max_sells":    self._safety.max_daily_sells,
            "halted":       self._halted,
        }
