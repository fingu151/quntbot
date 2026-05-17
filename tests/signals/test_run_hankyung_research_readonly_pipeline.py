from __future__ import annotations

import pytest

from scripts import run_hankyung_research_readonly_pipeline as pipeline


def test_build_pipeline_steps_passes_hankyung_arguments(tmp_path):
    args = pipeline.parse_args(
        [
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-14",
            "--as-of-date",
            "2026-05-14",
            "--summary-output",
            str(tmp_path / "summary.md"),
            "--factor-output",
            str(tmp_path / "factor.md"),
            "--database-url",
            "sqlite:///:memory:",
        ]
    )

    steps = pipeline.build_pipeline_steps(args)

    assert [step.name for step in steps] == [
        "sync",
        "reanalyze",
        "summary",
        "factor_impact",
    ]
    assert "--include-pdf-text" in steps[0].argv
    assert steps[0].argv[steps[0].argv.index("--url") + 1] == "https://consensus.hankyung.com/"
    assert steps[0].argv[steps[0].argv.index("--start-date") + 1] == "2026-01-01"
    assert steps[0].argv[steps[0].argv.index("--end-date") + 1] == "2026-05-14"
    assert (
        steps[2].argv[steps[2].argv.index("--title") + 1]
        == "Hankyung Consensus Research Summary"
    )
    assert steps[1].argv[steps[1].argv.index("--broker") + 1] == ""
    assert steps[2].argv[steps[2].argv.index("--broker") + 1] == ""
    assert steps[3].argv[steps[3].argv.index("--broker") + 1] == ""
    assert (
        steps[3].argv[steps[3].argv.index("--research-start-date") + 1]
        == "2026-01-01"
    )
    assert (
        steps[3].argv[steps[3].argv.index("--title") + 1]
        == "Hankyung Consensus Factor Impact"
    )
    assert all("sqlite:///:memory:" in step.argv for step in steps)


def test_run_executes_steps_in_order_without_orders(capsys):
    args = pipeline.parse_args(["--as-of-date", "2026-05-14"])
    called: list[str] = []

    def runner(name):
        def _run(argv):
            called.append(name)
            return 0

        return _run

    exit_code = pipeline.run(
        args,
        runners={
            "sync": runner("sync"),
            "reanalyze": runner("reanalyze"),
            "summary": runner("summary"),
            "factor_impact": runner("factor_impact"),
        },
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert called == ["sync", "reanalyze", "summary", "factor_impact"]
    assert "pipeline_status=completed" in out
    assert "orders_submitted=0" in out


def test_run_stops_on_failed_step(capsys):
    args = pipeline.parse_args(["--as-of-date", "2026-05-14"])

    exit_code = pipeline.run(
        args,
        runners={
            "sync": lambda _argv: 0,
            "reanalyze": lambda _argv: 2,
            "summary": lambda _argv: pytest.fail("summary should not run"),
            "factor_impact": lambda _argv: pytest.fail("factor should not run"),
        },
    )

    out = capsys.readouterr().out
    assert exit_code == 2
    assert "pipeline_status=failed failed_step=reanalyze" in out
    assert "orders_submitted=0" in out
