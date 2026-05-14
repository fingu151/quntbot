from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace


def test_agent_ops_streamlit_dashboard_module_does_not_import_trading_helpers():
    source = Path("scripts/agent_ops_streamlit_dashboard.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    forbidden_names = {
        "KisClient",
        "TradingEngine",
        "execute_rebalance",
        "src.trading",
        "src.data.database",
    }

    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module:
                imported_names.add(node.module)
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)

    assert forbidden_names.isdisjoint(imported_names)


def test_render_dashboard_shows_status_work_and_evidence(monkeypatch, tmp_path):
    import scripts.agent_ops_streamlit_dashboard as streamlit_dashboard
    import scripts.generate_agent_ops_dashboard as model_builder

    calls: list[tuple[str, tuple, dict]] = []

    class FakeColumn:
        def __enter__(self):
            calls.append(("column_enter", (), {}))
            return self

        def __exit__(self, exc_type, exc, tb):
            calls.append(("column_exit", (), {}))
            return False

        def __getattr__(self, name):
            def _inner(*args, **kwargs):
                calls.append((name, args, kwargs))

            return _inner

    def record(name):
        def _inner(*args, **kwargs):
            calls.append((name, args, kwargs))
            if name == "columns":
                count = len(args[0]) if isinstance(args[0], list) else args[0]
                return [FakeColumn() for _ in range(count)]
            return None

        return _inner

    fake_streamlit = SimpleNamespace(
        set_page_config=record("set_page_config"),
        title=record("title"),
        caption=record("caption"),
        subheader=record("subheader"),
        markdown=record("markdown"),
        metric=record("metric"),
        columns=record("columns"),
        dataframe=record("dataframe"),
        warning=record("warning"),
        success=record("success"),
        error=record("error"),
        code=record("code"),
    )
    monkeypatch.setitem(__import__("sys").modules, "streamlit", fake_streamlit)

    dry_run = tmp_path / "dry_run.json"
    progress = tmp_path / "progress.md"
    dry_run.write_text(
        (
            '{"dry_run": true, "as_of_date": "2026-05-13", '
            '"price_lookup_failed_count": 0, "price_fallback_count": 0}'
        ),
        encoding="utf-8",
    )
    progress.write_text(
        "# quntbot Progress Log\n\n"
        "## 2026-05-13 Dashboard work\n\n"
        "### Completed\n\n"
        "- added Streamlit dashboard\n\n"
        "### Verification\n\n"
        "- targeted tests passed\n",
        encoding="utf-8",
    )
    model = model_builder.build_dashboard_model(
        dry_run_json=dry_run,
        expected_date="2026-05-13",
        progress_path=progress,
        handoff_path=tmp_path / "HANDOFF_FOR_AGENTS.md",
        comparison_path=tmp_path / "rebalance_comparison_latest.md",
    )

    streamlit_dashboard.render_dashboard(model)

    rendered_text = "\n".join(str(arg) for _, args, _ in calls for arg in args)
    assert "에이전트 작업 연속성 대시보드" in rendered_text
    assert "★ 지금 확인할 것" in rendered_text
    assert "전체 안전 상태" in rendered_text
    assert "Streamlit 대시보드를 추가했습니다" in rendered_text
    assert "대상 테스트가 통과했습니다" in rendered_text
    assert "dry-run JSON" in rendered_text
    assert "O 완료" in rendered_text


def test_main_sets_page_config_before_sidebar(monkeypatch, tmp_path):
    import scripts.agent_ops_streamlit_dashboard as streamlit_dashboard
    import scripts.generate_agent_ops_dashboard as model_builder

    calls: list[str] = []

    class FakeSidebar:
        def header(self, *args, **kwargs):
            calls.append("sidebar.header")

        def text_input(self, label, value):
            calls.append(f"sidebar.text_input:{label}")
            if label == "Expected date":
                return "2026-05-13"
            return str(tmp_path / "dry_run.json")

    def record(name):
        def _inner(*args, **kwargs):
            calls.append(name)
            if name == "columns":
                return [FakeColumn() for _ in range(4)]
            return None

        return _inner

    class FakeColumn:
        def __enter__(self):
            calls.append("column_enter")
            return self

        def __exit__(self, exc_type, exc, tb):
            calls.append("column_exit")
            return False

        def metric(self, *args, **kwargs):
            calls.append("metric")

    fake_streamlit = SimpleNamespace(
        sidebar=FakeSidebar(),
        set_page_config=record("set_page_config"),
        title=record("title"),
        caption=record("caption"),
        subheader=record("subheader"),
        markdown=record("markdown"),
        metric=record("metric"),
        columns=record("columns"),
        dataframe=record("dataframe"),
        warning=record("warning"),
        success=record("success"),
        error=record("error"),
        code=record("code"),
    )
    monkeypatch.setitem(__import__("sys").modules, "streamlit", fake_streamlit)

    dry_run = tmp_path / "dry_run.json"
    dry_run.write_text(
        (
            '{"dry_run": true, "as_of_date": "2026-05-13", '
            '"price_lookup_failed_count": 0, "price_fallback_count": 0}'
        ),
        encoding="utf-8",
    )
    model = model_builder.build_dashboard_model(
        dry_run_json=dry_run,
        expected_date="2026-05-13",
        progress_path=tmp_path / "progress.md",
        handoff_path=tmp_path / "HANDOFF_FOR_AGENTS.md",
        comparison_path=tmp_path / "rebalance_comparison_latest.md",
    )
    monkeypatch.setattr(streamlit_dashboard, "build_dashboard_model", lambda **_kwargs: model)

    streamlit_dashboard.main()

    assert calls.index("set_page_config") < calls.index("sidebar.header")
