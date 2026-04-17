from agents.python.monte_carlo import kelly_fraction, run_monte_carlo


def test_run_monte_carlo_empty_returns():
    report = run_monte_carlo([], initial_capital=100_000, horizon_days=252, simulations=100)
    assert report.simulations == 100
    assert report.median_final == 100_000


def test_run_monte_carlo_positive_returns():
    returns = [0.001, 0.002, -0.0005, 0.0015, 0.001] * 20
    report = run_monte_carlo(returns, initial_capital=100_000, horizon_days=100, simulations=200, seed=42)
    assert report.simulations == 200
    assert report.prob_profit > 0.5
    assert report.median_final > 0


def test_run_monte_carlo_negative_returns():
    returns = [-0.005, -0.003, 0.001, -0.002, -0.001] * 20
    report = run_monte_carlo(returns, initial_capital=100_000, horizon_days=100, simulations=200, seed=42)
    assert report.prob_profit < 0.5


def test_run_monte_carlo_summary_keys():
    returns = [0.001, -0.0005, 0.0015, 0.0] * 10
    report = run_monte_carlo(returns, initial_capital=100_000, horizon_days=50, simulations=100)
    summary = report.summary()
    for key in [
        "simulations",
        "median_final",
        "mean_final",
        "p5_final",
        "p95_final",
        "expected_return_pct",
        "var_95_pct",
        "cvar_95_pct",
        "prob_profit_pct",
        "prob_dd_over_10_pct",
        "prob_dd_over_20_pct",
    ]:
        assert key in summary


def test_kelly_fraction_positive_edge():
    result = kelly_fraction(win_rate=0.6, avg_win=100, avg_loss=-50)
    assert 0 < result <= 0.25


def test_kelly_fraction_negative_edge():
    result = kelly_fraction(win_rate=0.3, avg_win=50, avg_loss=-100)
    assert result == 0.0


def test_kelly_fraction_zero_inputs():
    assert kelly_fraction(win_rate=0.5, avg_win=100, avg_loss=0) == 0.0
    assert kelly_fraction(win_rate=0, avg_win=100, avg_loss=-50) == 0.0


def test_kelly_fraction_capped_at_25_pct():
    result = kelly_fraction(win_rate=0.9, avg_win=200, avg_loss=-10)
    assert result <= 0.25
