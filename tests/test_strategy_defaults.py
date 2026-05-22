from config import EXIT_RULES, REBALANCE, SAFETY


def test_adopted_exit_strategy_defaults_match_tuned_adaptive_alpha():
    assert EXIT_RULES.stop_loss_pct == -0.07
    assert EXIT_RULES.trailing_stop_pct == -0.08
    assert EXIT_RULES.stop_cooldown_days == 3
    assert EXIT_RULES.profit_take_pct == 0.16
    assert EXIT_RULES.profit_take_sell_fraction == 0.45
    assert EXIT_RULES.breakeven_stop_pct == 0.0
    assert EXIT_RULES.enable_atr_stop is True
    assert EXIT_RULES.atr_window == 14
    assert EXIT_RULES.atr_multiplier == 2.2
    assert REBALANCE.sell_rank_buffer == 40
    assert SAFETY.max_daily_buys == 20
