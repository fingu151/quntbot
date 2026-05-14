from argparse import Namespace

from scripts.sync_korean_research_reports import parse_args, run
from src.data.database import get_engine


def test_parse_args_accepts_required_research_report_options():
    args = parse_args(
        [
            "--url",
            "https://example.test/research",
            "--source",
            "mirae_kr",
            "--broker",
            "미래에셋증권",
            "--database-url",
            "sqlite:///:memory:",
            "--include-pdf-text",
        ]
    )

    assert args.url == "https://example.test/research"
    assert args.source == "mirae_kr"
    assert args.broker == "미래에셋증권"
    assert args.database_url == "sqlite:///:memory:"
    assert args.include_pdf_text is True


def test_parse_args_uses_hankyung_defaults():
    args = parse_args([])

    assert args.url == "https://markets.hankyung.com/consensus"
    assert args.source == "hankyung_consensus"
    assert args.broker == "한경 컨센서스"
    assert args.include_pdf_text is False


def test_run_reports_stored_rows_without_orders(capsys):
    def engine_factory(database_url):
        return get_engine("sqlite:///:memory:")

    def report_fetcher(engine, *, url, source, broker, include_pdf_text, pdf_telemetry):
        assert url == "https://example.test/research"
        assert source == "mirae_kr"
        assert broker == "미래에셋증권"
        assert include_pdf_text is True
        pdf_telemetry.pdf_text_attempted = 2
        pdf_telemetry.pdf_text_extracted = 1
        pdf_telemetry.pdf_text_length = 1234
        pdf_telemetry.body_signal_applied = 1
        pdf_telemetry.analysis_rows_stored = 3
        pdf_telemetry.analysis_success_count = 3
        pdf_telemetry.analysis_failed_count = 0
        return 3

    exit_code = run(
        Namespace(
            url="https://example.test/research",
            source="mirae_kr",
            broker="미래에셋증권",
            database_url=None,
            include_pdf_text=True,
        ),
        engine_factory=engine_factory,
        report_fetcher=report_fetcher,
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "korean_research_report_rows_stored=3" in captured.out
    assert "pdf_text_attempted=2" in captured.out
    assert "pdf_text_extracted=1" in captured.out
    assert "pdf_text_length=1234" in captured.out
    assert "body_signal_applied=1" in captured.out
    assert "analysis_rows_stored=3" in captured.out
    assert "analysis_success_count=3" in captured.out
    assert "analysis_failed_count=0" in captured.out
    assert "orders_submitted=0" in captured.out
