from __future__ import annotations

from datetime import date
from pathlib import Path

from config import DATA_DIR
from scripts.generate_agent_ops_dashboard import (
    DashboardModel,
    build_dashboard_model,
    _display_status,
    _ko_text,
    _task_group_label,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DRY_RUN_PATH = DATA_DIR / "dry_run_rebalance_latest.json"
DEFAULT_MIRAE_SUMMARY_PATH = DATA_DIR / "mirae_research_summary_latest.md"


def render_dashboard(
    model: DashboardModel, *, mirae_summary_path: Path | None = None
) -> None:
    import streamlit as st

    st.title("에이전트 작업 연속성 대시보드")
    st.caption(
        "로컬 파일만 읽어서 현재 상태, 작업 이력, 근거, 다음 안전 명령을 보여줍니다."
    )

    safety = model.current_state["overall_local_safety"]
    if safety == "clean":
        st.success("전체 안전 상태: O 완료")
    elif safety == "blocked":
        st.error("전체 안전 상태: X 막힘")
    else:
        st.warning(f"전체 안전 상태: {_display_status(safety)}")

    columns = st.columns(4)
    metrics = [
        ("매매 모드", model.current_state["trade_mode"]),
        ("dry-run 기준일", model.current_state["dry_run_as_of_date"]),
        ("가격 조회 실패", model.current_state["price_lookup_failures"]),
        ("대체 가격 사용", model.current_state["fallback_prices"]),
    ]
    for column, (label, value) in zip(columns, metrics):
        with column:
            st.metric(label, value)

    st.subheader("지금 확인할 것")
    st.markdown(f"**최근 작업:** `{model.latest_progress_title}`")
    st.markdown(f"**다음 안전 명령:** `{model.next_safe_command}`")

    st.subheader("현재 상태")
    st.dataframe(_current_state_rows(model), hide_index=True, use_container_width=True)

    st.subheader("작업 이어가기")
    st.markdown("**O 완료된 것**")
    st.markdown(_markdown_bullets(model.completed_items))
    st.markdown("**△ 검증 또는 진행 중**")
    st.markdown(_markdown_bullets(model.verification_items, marker="△ 확인"))
    st.markdown("**☆ 중요 메모와 주의점**")
    st.markdown(_markdown_bullets(model.note_items, marker="☆ 중요"))

    st.subheader("하기로 한 일")
    st.dataframe(_task_lane_rows(model), hide_index=True, use_container_width=True)

    if mirae_summary_path is not None:
        _render_mirae_research_summary(mirae_summary_path)

    st.subheader("근거")
    st.dataframe(_evidence_rows(model), hide_index=True, use_container_width=True)

    st.subheader("타임라인")
    st.dataframe(_timeline_rows(model), hide_index=True, use_container_width=True)

    st.subheader("다음 안전 명령")
    st.code(model.next_safe_command, language="powershell")

    if model.warnings:
        st.subheader("X 확인 필요")
        for warning in model.warnings:
            st.warning(f"X 막힘 {warning}")


def main() -> None:
    import streamlit as st

    st.set_page_config(
        page_title="에이전트 작업 연속성 대시보드",
        page_icon="Q",
        layout="wide",
    )
    st.sidebar.header("입력")
    expected_date = st.sidebar.text_input("기준일", value=str(date.today()))
    dry_run_path = Path(
        st.sidebar.text_input("dry-run JSON", value=str(DEFAULT_DRY_RUN_PATH))
    )
    mirae_summary_path = Path(
        st.sidebar.text_input(
            "미래에셋 요약 Markdown", value=str(DEFAULT_MIRAE_SUMMARY_PATH)
        )
    )
    model = build_dashboard_model(
        dry_run_json=dry_run_path,
        expected_date=expected_date,
    )
    render_dashboard(model, mirae_summary_path=mirae_summary_path)


def _render_mirae_research_summary(path: Path) -> None:
    import streamlit as st

    meta_rows, report_rows, warnings = load_mirae_summary_markdown(path)

    st.subheader("미래에셋 리서치 요약")
    if warnings:
        for warning in warnings:
            st.warning(warning)
        return

    st.markdown(_markdown_bullets(meta_rows, marker="☆ 요약"))
    if report_rows:
        st.dataframe(report_rows, hide_index=True, use_container_width=True)
    else:
        st.warning("X 막힘 미래에셋 리서치 요약 표가 비어 있습니다.")


def load_mirae_summary_markdown(
    path: Path, *, max_rows: int = 20
) -> tuple[list[str], list[dict[str, str]], list[str]]:
    if not path.exists():
        return [], [], [f"X 막힘 요약 파일 없음: {path}"]

    text = path.read_text(encoding="utf-8", errors="replace")
    meta_rows = [
        line[2:].strip()
        for line in text.splitlines()
        if line.startswith("- ") and "orders_submitted" not in line
    ]

    report_rows: list[dict[str, str]] = []
    in_table = False
    for line in text.splitlines():
        if line.startswith("| date | ticker | opinion | body | confidence |"):
            in_table = True
            continue
        if not in_table or not line.startswith("|"):
            continue
        if line.startswith("| ---"):
            continue
        cells = _split_markdown_row(line)
        if len(cells) < 5:
            continue
        detail = " | ".join(cells[5:]).strip()
        report_rows.append(
            {
                "날짜": cells[0],
                "종목코드": cells[1],
                "의견": cells[2],
                "본문": cells[3],
                "신뢰도": cells[4],
                "핵심 내용": _truncate(detail, 240),
            }
        )
        if len(report_rows) >= max_rows:
            break

    return meta_rows, report_rows, []


def _split_markdown_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1].rstrip() + "..."


def _current_state_rows(model: DashboardModel) -> list[dict[str, str]]:
    return [
        {
            "항목": "TRADE_MODE",
            "상태": _display_status(model.current_state["trade_mode_status"]),
            "값": model.current_state["trade_mode"],
        },
        {
            "항목": "dry-run 보고서",
            "상태": _display_status(model.current_state["dry_run_status"]),
            "값": str(model.dry_run_summary.path),
        },
        {
            "항목": "dry-run 기준일",
            "상태": _display_status(model.current_state["dry_run_date_status"]),
            "값": model.current_state["dry_run_as_of_date"],
        },
        {
            "항목": "최근 검증",
            "상태": _display_status("inferred"),
            "값": _ko_text(model.current_state["latest_verification"]),
        },
        {
            "항목": "전체 안전 상태",
            "상태": _display_status(model.current_state["overall_local_safety"]),
            "값": "브로커 API/주문 호출 없음",
        },
    ]


def _task_lane_rows(model: DashboardModel) -> list[dict[str, str]]:
    return [
        {
            "묶음": _task_group_label(group),
            "상태": _display_status(values["status"]),
            "근거": _ko_text(values["evidence"]),
        }
        for group, values in model.task_lanes.items()
    ]


def _evidence_rows(model: DashboardModel) -> list[dict[str, str]]:
    return [
        {
            "항목": item["item"],
            "상태": _display_status(item["status"]),
            "경로": item["path"],
        }
        for item in model.evidence
    ]


def _timeline_rows(model: DashboardModel) -> list[dict[str, str]]:
    return [
        {
            "이벤트": item["event"],
            "상태": _display_status(item["status"]),
            "출처": item["source"],
        }
        for item in model.timeline
    ]


def _markdown_bullets(items: list[str], *, marker: str = "O 완료") -> str:
    if not items:
        return f"- {marker} 없음"
    return "\n".join(f"- {marker} {_ko_text(item)}" for item in items)


if __name__ == "__main__":
    main()
