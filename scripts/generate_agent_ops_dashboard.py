from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DATA_DIR, TRADE_MODE


@dataclass(frozen=True)
class DryRunSummary:
    path: Path
    status: str
    safety_status: str
    as_of_date: str | None = None
    target_count: int | None = None
    sell_count: int | None = None
    buy_count: int | None = None
    skipped_buy_count: int | None = None
    price_lookup_failed_count: int | None = None
    price_fallback_count: int | None = None
    price_retry_success_count: int | None = None
    price_retry_failed_count: int | None = None
    error: str | None = None


@dataclass(frozen=True)
class ProgressSummary:
    title: str
    completed_items: list[str]
    verification_items: list[str]
    note_items: list[str]
    status: str = "missing"
    error: str | None = None


@dataclass(frozen=True)
class DashboardModel:
    expected_date: str
    generated_for_date: str
    current_trade_mode: str
    dry_run_summary: DryRunSummary
    latest_progress_title: str
    completed_items: list[str]
    verification_items: list[str]
    note_items: list[str]
    current_state: dict[str, str]
    task_lanes: dict[str, dict[str, str]]
    evidence: list[dict[str, str]]
    timeline: list[dict[str, str]]
    next_safe_command: str
    warnings: list[str]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a local-only Markdown dashboard for quntbot agent operations."
    )
    parser.add_argument(
        "--dry-run-json",
        type=Path,
        default=DATA_DIR / "dry_run_rebalance_latest.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_DIR / "agent_ops_dashboard_latest.md",
    )
    parser.add_argument("--expected-date", default=str(date.today()))
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the generated dashboard in Notepad after writing it.",
    )
    return parser.parse_args(argv)


def load_dry_run_summary(path: Path) -> DryRunSummary:
    if not path.exists():
        return DryRunSummary(path=path, status="missing", safety_status="unknown")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return DryRunSummary(
            path=path,
            status="read-error",
            safety_status="blocked",
            error=str(exc),
        )

    try:
        failed_count = _optional_int(payload, "price_lookup_failed_count")
        fallback_count = _optional_int(payload, "price_fallback_count")
        if failed_count is None or fallback_count is None:
            safety_status = "unknown"
        elif failed_count == 0 and fallback_count == 0 and payload.get("dry_run") is True:
            safety_status = "clean"
        else:
            safety_status = "blocked"

        return DryRunSummary(
            path=path,
            status="present",
            safety_status=safety_status,
            as_of_date=_optional_str(payload, "as_of_date"),
            target_count=_optional_int(payload, "target_count"),
            sell_count=_optional_int(payload, "sell_count"),
            buy_count=_optional_int(payload, "buy_count"),
            skipped_buy_count=_optional_int(payload, "skipped_buy_count"),
            price_lookup_failed_count=failed_count,
            price_fallback_count=fallback_count,
            price_retry_success_count=_optional_int(payload, "price_retry_success_count"),
            price_retry_failed_count=_optional_int(payload, "price_retry_failed_count"),
        )
    except (TypeError, ValueError) as exc:
        return DryRunSummary(
            path=path,
            status="read-error",
            safety_status="blocked",
            error=str(exc),
        )


def build_dashboard_model(
    *,
    dry_run_json: Path,
    expected_date: str,
    progress_path: Path = ROOT_DIR / "progress.md",
    handoff_path: Path = ROOT_DIR / "HANDOFF_FOR_AGENTS.md",
    comparison_path: Path = DATA_DIR / "rebalance_comparison_latest.md",
) -> DashboardModel:
    summary = load_dry_run_summary(dry_run_json)
    progress = load_progress_summary(progress_path)
    overall_safety = _overall_safety_status(summary, expected_date)
    next_safe_command = (
        ".\\venv\\Scripts\\python.exe scripts\\check_rebalance_readiness.py "
        f"--dry-run-json {_rel(summary.path)} --expected-date {expected_date}"
    )
    current_state = {
        "trade_mode": TRADE_MODE,
        "trade_mode_status": _status_bool(TRADE_MODE == "PAPER"),
        "dry_run_status": summary.status,
        "dry_run_as_of_date": summary.as_of_date or "unknown",
        "dry_run_date_status": _date_status(summary.as_of_date, expected_date),
        "price_lookup_failures": _fmt(summary.price_lookup_failed_count),
        "fallback_prices": _fmt(summary.price_fallback_count),
        "overall_local_safety": overall_safety,
        "latest_verification": progress.verification_items[0]
        if progress.verification_items
        else "unknown",
    }
    task_lanes = {
        "needs_input": {
            "status": "clean" if overall_safety == "clean" else "needs-review",
            "evidence": "blocked, stale, or unknown safety fields appear here",
        },
        "running": {
            "status": "inferred",
            "evidence": progress.title or "latest dry-run/report review flow",
        },
        "backlog": {
            "status": "inferred",
            "evidence": "next safe command and handoff-described follow-up",
        },
        "scheduled": {
            "status": "inferred",
            "evidence": "handoff-described recurring work",
        },
        "done": {
            "status": "inferred",
            "evidence": progress.completed_items[0]
            if progress.completed_items
            else "latest generated local reports",
        },
    }
    warnings = []
    if summary.error:
        warnings.append(f"dry-run read error: {summary.error}")
    if progress.error:
        warnings.append(f"progress read error: {progress.error}")
    for path, label in (
        (handoff_path, "handoff"),
        (comparison_path, "rebalance comparison"),
    ):
        if not path.exists():
            warnings.append(f"{label} missing: {_rel(path)}")

    return DashboardModel(
        expected_date=expected_date,
        generated_for_date=expected_date,
        current_trade_mode=TRADE_MODE,
        dry_run_summary=summary,
        latest_progress_title=progress.title or "unknown",
        completed_items=progress.completed_items,
        verification_items=progress.verification_items,
        note_items=progress.note_items,
        current_state=current_state,
        task_lanes=task_lanes,
        evidence=[
            {"item": "dry-run JSON", "status": summary.status, "path": _rel(summary.path)},
            {
                "item": "agent roster",
                "status": _path_status(ROOT_DIR / "docs" / "agent-roster.md"),
                "path": "docs/agent-roster.md",
            },
            {"item": "handoff", "status": _path_status(handoff_path), "path": _rel(handoff_path)},
            {"item": "progress", "status": progress.status, "path": _rel(progress_path)},
            {
                "item": "rebalance comparison",
                "status": _path_status(comparison_path),
                "path": _rel(comparison_path),
            },
        ],
        timeline=[
            {"event": "latest progress", "status": progress.status, "source": progress.title or _rel(progress_path)},
            {"event": "latest dry-run report", "status": summary.status, "source": _rel(summary.path)},
            {
                "event": "rebalance comparison",
                "status": _path_status(comparison_path),
                "source": _rel(comparison_path),
            },
            {"event": "handoff notes", "status": _path_status(handoff_path), "source": _rel(handoff_path)},
        ],
        next_safe_command=next_safe_command,
        warnings=warnings,
    )


def load_progress_summary(path: Path) -> ProgressSummary:
    if not path.exists():
        return ProgressSummary(
            title="",
            completed_items=[],
            verification_items=[],
            note_items=[],
            status="missing",
        )
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return ProgressSummary(
            title="",
            completed_items=[],
            verification_items=[],
            note_items=[],
            status="read-error",
            error=str(exc),
        )
    return _parse_latest_progress(text)


def _parse_latest_progress(text: str) -> ProgressSummary:
    title = ""
    sections: dict[str, list[str]] = {"completed": [], "verification": [], "notes": []}
    active: str | None = None
    in_latest = False
    for line in text.splitlines():
        if line.startswith("## "):
            if in_latest:
                break
            title = line.removeprefix("## ").strip()
            in_latest = True
            active = None
            continue
        if not in_latest:
            continue
        lowered = line.strip().lower()
        if lowered.startswith("### "):
            heading = lowered.removeprefix("### ").strip()
            if heading == "completed":
                active = "completed"
            elif heading == "verification":
                active = "verification"
            elif heading == "notes":
                active = "notes"
            else:
                active = None
            continue
        if active and line.startswith("- "):
            sections[active].append(line[2:].strip())
            continue
        if active and sections[active] and line.startswith("  - "):
            sections[active][-1] += f"; {line.strip()[2:].strip()}"
            continue
        if active and sections[active] and line.startswith("  ") and line.strip():
            sections[active][-1] += f" {line.strip()}"
    return ProgressSummary(
        title=title,
        completed_items=sections["completed"],
        verification_items=sections["verification"],
        note_items=sections["notes"],
        status="present",
    )


def render_dashboard_model(model: DashboardModel) -> str:
    summary = model.dry_run_summary
    overall_status = _display_status(model.current_state["overall_local_safety"])
    lines = [
        "# 에이전트 작업 연속성 대시보드",
        "",
        "## ★ 지금 확인할 것",
        "",
        f"- 기준일: `{model.generated_for_date}`",
        f"- 전체 안전 상태: **{overall_status}**",
        f"- 최근 작업: `{model.latest_progress_title}`",
        f"- 다음 안전 명령: `{model.next_safe_command}`",
        "",
        "## 현재 상태",
        "",
        "| 항목 | 상태 | 값 |",
        "| --- | --- | --- |",
        f"| 매매 모드 | {_display_status(model.current_state['trade_mode_status'])} | `{model.current_state['trade_mode']}` |",
        f"| dry-run 보고서 | {_display_status(summary.status)} | `{_rel(summary.path)}` |",
        f"| dry-run 기준일 | {_display_status(model.current_state['dry_run_date_status'])} | `{model.current_state['dry_run_as_of_date']}` |",
        f"| 가격 조회 실패 | {_display_status(_count_status(summary.price_lookup_failed_count))} | `{model.current_state['price_lookup_failures']}` |",
        f"| 대체 가격 사용 | {_display_status(_count_status(summary.price_fallback_count))} | `{model.current_state['fallback_prices']}` |",
        f"| 최근 검증 | {_display_status('inferred')} | `{model.current_state['latest_verification']}` |",
        f"| 전체 안전 상태 | {overall_status} | 브로커/API/주문 호출 없음 |",
        "",
        "## 에이전트 역할",
        "",
        "| 역할 | 목적 |",
        "| --- | --- |",
        "| Planner | 수정 전 범위와 순서 정리 |",
        "| Bug Investigator | 오류 재현과 원인 확인 |",
        "| Data and DB | DB/데이터 근거 확인 |",
        "| Strategy and Factor | 점수와 랭킹 영향 확인 |",
        "| Backtest | 과거 시뮬레이션 가정 확인 |",
        "| Trading Safety | PAPER/LIVE 주문 경로 보호 |",
        "| Research Brief | 근거 기반 리서치 요약 |",
        "| Portfolio Review | 리밸런싱 보고서 검토 |",
        "| Operations | 실행 명령과 산출물 관리 |",
        "| Test and Verification | 완료 전 검증 |",
        "| Docs and Handoff | 작업 맥락 보존 |",
        "",
        "## 하기로 한 일",
        "",
        "| 묶음 | 상태 | 근거 |",
        "| --- | --- | --- |",
    ]
    for group, lane in model.task_lanes.items():
        lines.append(
            f"| {_task_group_label(group)} | {_display_status(lane['status'])} | {_ko_text(lane['evidence'])} |"
        )
    lines.extend(
        [
            "",
            "## 작업 이어가기",
            "",
            f"- 최근 작업: `{model.latest_progress_title}`",
            "",
            "### O 완료된 것",
            "",
        ]
    )
    lines.extend(_bullet_lines(model.completed_items, marker="O 완료"))
    lines.extend(["", "### △ 검증/확인 상태", ""])
    lines.extend(_bullet_lines(model.verification_items, marker="△ 확인"))
    lines.extend(["", "### ★ 메모와 주의점", ""])
    lines.extend(_bullet_lines(model.note_items, marker="★ 중요"))
    lines.extend(
        [
            "",
            "## 근거",
            "",
            "| 항목 | 상태 | 경로 |",
            "| --- | --- | --- |",
        ]
    )
    for item in model.evidence:
        lines.append(
            f"| {item['item']} | {_display_status(item['status'])} | `{item['path']}` |"
        )
    lines.extend(
        [
            "",
            "## 안전 게이트",
            "",
            "| 게이트 | 상태 | 값 |",
            "| --- | --- | --- |",
            f"| TRADE_MODE=PAPER | {_display_status(_status_bool(TRADE_MODE == 'PAPER'))} | `{TRADE_MODE}` |",
            f"| dry-run 보고서 | {_display_status(summary.status)} | `{_rel(summary.path)}` |",
            f"| dry-run 기준일 | {_display_status(_date_status(summary.as_of_date, model.expected_date))} | `{summary.as_of_date or 'unknown'}` |",
            f"| 가격 조회 실패 | {_display_status(_count_status(summary.price_lookup_failed_count))} | `{_fmt(summary.price_lookup_failed_count)}` |",
            f"| 대체 가격 사용 | {_display_status(_count_status(summary.price_fallback_count))} | `{_fmt(summary.price_fallback_count)}` |",
            f"| 전체 로컬 안전 | {_display_status(_overall_safety_status(summary, model.expected_date))} | 브로커 호출 없음 |",
            "",
            "## 다음 안전 명령",
            "",
            "```powershell",
            model.next_safe_command,
            "```",
            "",
            "## 타임라인",
            "",
            "| 이벤트 | 상태 | 출처 |",
            "| --- | --- | --- |",
        ]
    )
    for item in model.timeline:
        lines.append(
            f"| {item['event']} | {_display_status(item['status'])} | `{item['source']}` |"
        )
    if model.warnings:
        lines.extend(["", "## X 확인 필요", ""])
        lines.extend(f"- X 막힘 {warning}" for warning in model.warnings)
    return "\n".join(lines) + "\n"


def render_dashboard(summary: DryRunSummary, *, expected_date: str) -> str:
    model = _model_from_summary(summary, expected_date=expected_date)
    return render_dashboard_model(model)


def run(
    args: argparse.Namespace, *, opener: Callable[[Path], object] | None = None
) -> int:
    model = build_dashboard_model(
        dry_run_json=args.dry_run_json,
        expected_date=str(args.expected_date),
    )
    summary = model.dry_run_summary
    markdown = render_dashboard_model(model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown, encoding="utf-8")
    print(f"dashboard_written={args.output}")
    if args.open:
        try:
            (opener or open_dashboard)(args.output)
        except OSError as exc:
            print(f"dashboard_open_failed={exc}")
        else:
            print(f"dashboard_opened={args.output}")
    print(f"dry_run_status={summary.status}")
    print(f"safety_status={_overall_safety_status(summary, str(args.expected_date))}")
    return 0


def open_dashboard(path: Path) -> None:
    subprocess.Popen(["notepad.exe", str(path)])


def _optional_int(payload: dict[str, Any], key: str) -> int | None:
    if key not in payload or payload[key] is None:
        return None
    try:
        return int(payload[key])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key}: {exc}") from exc


def _optional_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return str(value) if value is not None else None


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT_DIR.resolve()))
    except ValueError:
        return str(path)


def _path_status(path: Path) -> str:
    return "present" if path.exists() else "missing"


def _status_bool(value: bool) -> str:
    return "clean" if value else "blocked"


def _date_status(actual: str | None, expected: str) -> str:
    if actual is None:
        return "unknown"
    return "clean" if actual == expected else "stale-risk"


def _count_status(value: int | None) -> str:
    if value is None:
        return "unknown"
    return "clean" if value == 0 else "blocked"


def _overall_safety_status(summary: DryRunSummary, expected_date: str) -> str:
    if summary.safety_status == "blocked":
        return "blocked"
    date_status = _date_status(summary.as_of_date, expected_date)
    if date_status in {"blocked", "stale-risk"}:
        return "blocked"
    if summary.safety_status == "clean" and date_status == "clean":
        return "clean"
    return "unknown"


def _fmt(value: int | None) -> str:
    return "unknown" if value is None else str(value)


def _display_status(status: str) -> str:
    normalized = str(status).lower()
    if normalized in {"clean", "present", "ok", "passed"}:
        return "O 완료"
    if normalized in {"blocked", "read-error", "missing", "failed", "needs-review"}:
        return "X 막힘"
    if normalized == "stale-risk":
        return "X 오래됨"
    if normalized in {"inferred", "unknown"}:
        return "△ 추정"
    if normalized in {"running", "partial"}:
        return "△ 진행중"
    return f"△ {status}"


_TEXT_TRANSLATIONS = {
    "added Streamlit dashboard": "Streamlit 대시보드를 추가했습니다",
    "Added a read-only Streamlit dashboard:": "읽기 전용 Streamlit 대시보드를 추가했습니다:",
    "targeted tests passed": "대상 테스트가 통과했습니다",
    "tests passed": "테스트가 통과했습니다",
    "model added": "모델을 추가했습니다",
    "improved Markdown dashboard": "Markdown 대시보드를 개선했습니다",
    "added Streamlit dashboard": "Streamlit 대시보드를 추가했습니다",
    "continue with browser verification later": "나중에 브라우저 검증을 이어가야 합니다",
    "Localized the work continuity dashboard UI to Korean and changed status display to the requested marker scheme:": "작업 연속성 대시보드 UI를 한국어로 바꾸고 요청한 상태 표시 체계를 적용했습니다:",
    "Updated both Markdown and Streamlit renderers to use the same status marker mapping.": "Markdown과 Streamlit 화면이 같은 상태 표시 규칙을 사용하도록 맞췄습니다.",
    "Extended the existing local-only agent operations dashboard into a work continuity dashboard.": "기존 로컬 전용 에이전트 운영 대시보드를 작업 연속성 대시보드로 확장했습니다.",
    "Added a shared dashboard model that captures:": "대시보드가 공통으로 사용할 작업 상태 모델을 추가했습니다:",
    "current safety state": "현재 안전 상태",
    "latest progress headline": "최근 작업 제목",
    "completed work": "완료된 작업",
    "verification notes": "검증 기록",
    "operator notes": "운영 메모",
    "evidence paths": "근거 파일 경로",
    "timeline rows": "타임라인 항목",
    "next safe command": "다음 안전 명령",
    "Improved the generated Markdown report at": "생성되는 Markdown 보고서를 개선했습니다:",
    "with Summary, Current State, Work Continuity, Evidence, Safety Gates, Timeline, and Next Safe Command sections.": "요약, 현재 상태, 작업 이어가기, 근거, 안전 게이트, 타임라인, 다음 안전 명령 섹션을 포함합니다.",
    "Added/updated targeted tests:": "대상 테스트를 추가/수정했습니다:",
    "Added design and implementation documents:": "설계와 구현 계획 문서를 추가했습니다:",
    "Updated `HANDOFF_FOR_AGENTS.md` with Markdown and Streamlit dashboard commands.": "`HANDOFF_FOR_AGENTS.md`에 Markdown/Streamlit 대시보드 실행 명령을 추가했습니다.",
    "The dashboard remains local-only and read-only. It does not call KIS, place orders, mutate the DB, or execute readiness checks automatically.": "대시보드는 계속 로컬 전용/읽기 전용입니다. KIS 호출, 주문, DB 변경, readiness 자동 실행을 하지 않습니다.",
    "Smoke generation is blocked for safety because the latest dry-run report is dated": "최신 dry-run 보고서 날짜가 기준일과 달라 안전상 막힌 상태입니다:",
    "The Streamlit server was verified during the smoke check, but this execution environment did not keep the background process alive after the check ended.": "Streamlit 서버는 smoke 확인 중 정상 응답을 확인했지만, 이 실행 환경에서는 확인 종료 후 백그라운드 프로세스가 유지되지 않았습니다.",
    "This folder is not a git repository, so no design or implementation commit was created.": "이 폴더는 git 저장소가 아니라 설계/구현 커밋을 만들 수 없었습니다.",
    "blocked, stale, or unknown safety fields appear here": "막힘, 오래됨, 알 수 없음 상태가 있으면 여기에서 먼저 확인합니다",
    "next safe command and handoff-described follow-up": "다음 안전 명령과 handoff에 적힌 후속 작업입니다",
    "handoff-described recurring work": "handoff에 적힌 반복/예정 작업입니다",
    "latest generated local reports": "최근 생성된 로컬 보고서입니다",
}


def _ko_text(text: str) -> str:
    parts = str(text).split("`")
    for index in range(0, len(parts), 2):
        translated = parts[index]
        for source, target in _TEXT_TRANSLATIONS.items():
            translated = translated.replace(source, target)
        parts[index] = translated
    return "`".join(parts)


def _task_group_label(group: str) -> str:
    labels = {
        "needs_input": "★ 확인 필요",
        "running": "△ 진행중",
        "backlog": "△ 다음 할 일",
        "scheduled": "△ 예정",
        "done": "O 완료",
    }
    return labels.get(group, group)


def _bullet_lines(items: Sequence[str], *, marker: str = "-") -> list[str]:
    if not items:
        return [f"- {marker} 없음"]
    return [f"- {marker} {_ko_text(item)}" for item in items]


def _model_from_summary(summary: DryRunSummary, *, expected_date: str) -> DashboardModel:
    progress = load_progress_summary(ROOT_DIR / "progress.md")
    overall_safety = _overall_safety_status(summary, expected_date)
    return DashboardModel(
        expected_date=expected_date,
        generated_for_date=expected_date,
        current_trade_mode=TRADE_MODE,
        dry_run_summary=summary,
        latest_progress_title=progress.title or "unknown",
        completed_items=progress.completed_items,
        verification_items=progress.verification_items,
        note_items=progress.note_items,
        current_state={
            "trade_mode": TRADE_MODE,
            "trade_mode_status": _status_bool(TRADE_MODE == "PAPER"),
            "dry_run_status": summary.status,
            "dry_run_as_of_date": summary.as_of_date or "unknown",
            "dry_run_date_status": _date_status(summary.as_of_date, expected_date),
            "price_lookup_failures": _fmt(summary.price_lookup_failed_count),
            "fallback_prices": _fmt(summary.price_fallback_count),
            "overall_local_safety": overall_safety,
            "latest_verification": progress.verification_items[0]
            if progress.verification_items
            else "unknown",
        },
        task_lanes={
            "needs_input": {
                "status": "clean" if overall_safety == "clean" else "needs-review",
                "evidence": "blocked, stale, or unknown safety fields appear here",
            },
            "running": {"status": "inferred", "evidence": progress.title or "unknown"},
            "backlog": {
                "status": "inferred",
                "evidence": "next safe command and docs updates",
            },
            "scheduled": {
                "status": "inferred",
                "evidence": "handoff-described recurring work",
            },
            "done": {
                "status": "inferred",
                "evidence": progress.completed_items[0]
                if progress.completed_items
                else "latest generated local reports",
            },
        },
        evidence=[
            {"item": "dry-run JSON", "status": summary.status, "path": _rel(summary.path)},
            {"item": "agent roster", "status": "present", "path": "docs/agent-roster.md"},
            {"item": "handoff", "status": "present", "path": "HANDOFF_FOR_AGENTS.md"},
            {"item": "progress", "status": progress.status, "path": "progress.md"},
        ],
        timeline=[
            {"event": "latest progress", "status": progress.status, "source": progress.title or "progress.md"},
            {"event": "latest dry-run report", "status": summary.status, "source": _rel(summary.path)},
            {
                "event": "rebalance comparison",
                "status": "inferred",
                "source": "data/rebalance_comparison_latest.md",
            },
            {"event": "handoff notes", "status": "present", "source": "HANDOFF_FOR_AGENTS.md"},
        ],
        next_safe_command=(
            ".\\venv\\Scripts\\python.exe scripts\\check_rebalance_readiness.py "
            f"--dry-run-json {_rel(summary.path)} --expected-date {expected_date}"
        ),
        warnings=[f"dry-run read error: {summary.error}"] if summary.error else [],
    )


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
