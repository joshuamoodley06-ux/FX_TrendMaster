"""Markdown report writer: inputs, counts, rule-model statistics, audits."""

from __future__ import annotations

from typing import Any

from analyst import __version__
from analyst.audit.audit_warnings import AuditWarning
from analyst.models.records import InputPackage
from analyst.util.timeparse import ms_to_iso


def build_year_report(
    package: InputPackage,
    yearly_stats: dict[str, Any],
    ledger_results: list[dict[str, Any]],
    warnings: list[AuditWarning],
) -> str:
    counts = yearly_stats.get("counts", {})
    lines: list[str] = []
    lines.append(f"# Analyst Report — {package.label}")
    lines.append("")
    lines.append(f"- Engine: Python Analyst {__version__}")
    lines.append(f"- Symbol: {package.symbol}")
    lines.append(f"- Year: {package.year if package.year is not None else 'unknown'}")
    lines.append(f"- Package generated: {ms_to_iso(package.generated_at_utc_ms) or 'unknown'}")
    lines.append(f"- Selected case_refs: {len(package.case_refs)}")
    lines.append("")

    lines.append("## Input counts")
    lines.append("")
    lines.append("| Item | Count |")
    lines.append("| --- | --- |")
    lines.append(f"| Ranges | {counts.get('ranges', 0)} |")
    lines.append(f"| Events | {counts.get('events', 0)} |")
    candle_counts = counts.get("candles", {})
    total_candles = sum(candle_counts.values()) if isinstance(candle_counts, dict) else 0
    lines.append(f"| Candles (total) | {total_candles} |")
    for timeframe, count in sorted(candle_counts.items() if isinstance(candle_counts, dict) else []):
        lines.append(f"| Candles {timeframe} | {count} |")
    lines.append(f"| Audit warnings | {counts.get('warnings', 0)} |")
    lines.append("")

    lines.append("## Selected cases")
    lines.append("")
    for ref in package.case_refs:
        range_count = sum(1 for r in package.ranges if r.case_ref == ref)
        event_count = sum(1 for e in package.events if e.case_ref == ref)
        lines.append(f"- `{ref}` — {range_count} ranges, {event_count} events")
    lines.append("")

    lines.extend(_rule_stats_section(yearly_stats.get("rule_stats") or {}))

    lines.append("## Raw ledger verification")
    lines.append("")
    if not ledger_results:
        lines.append("No raw ledgers embedded in this package.")
    else:
        lines.append("| Case ref | Status | Events |")
        lines.append("| --- | --- | --- |")
        for result in ledger_results:
            lines.append(
                f"| `{result.get('case_ref')}` | {result.get('status')} | {result.get('event_count', '-')} |"
            )
    lines.append("")

    lines.append("## Audit warnings")
    lines.append("")
    if not warnings:
        lines.append("No warnings.")
    else:
        lines.append("| Code | Case ref | Subject | Message |")
        lines.append("| --- | --- | --- | --- |")
        for warning in warnings:
            lines.append(
                f"| {warning.code} | {warning.case_ref or '-'} | {warning.subject_id or '-'} | {warning.message} |"
            )
    lines.append("")

    return "\n".join(lines)


def _counts_inline(counts: Any) -> str:
    if not isinstance(counts, dict) or not counts:
        return "none"
    return ", ".join(f"{key}: {value}" for key, value in sorted(counts.items()))


def _rule_stats_section(rule_stats: dict[str, Any]) -> list[str]:
    lines = ["## Rule model statistics", ""]

    zones = rule_stats.get("zones")
    if zones:
        lines.append(f"- Zones — children classified: {zones.get('children_classified', 0)}; "
                     f"start zones: {_counts_inline(zones.get('start_zone_counts'))}; "
                     f"break zones: {_counts_inline(zones.get('break_zone_counts'))}")

    metrics = rule_stats.get("range_metrics")
    if metrics:
        lines.append(f"- Range metrics — ranges measured: {metrics.get('ranges', 0)} "
                     f"across {len(metrics.get('by_layer') or {})} layer(s)")

    parent_child = rule_stats.get("parent_child")
    if parent_child:
        lines.append(f"- Parent/child — parents with children: {parent_child.get('parents_with_children', 0)}; "
                     f"total children: {parent_child.get('total_children', 0)}; "
                     f"avg per parent: {parent_child.get('avg_children_per_parent')}; "
                     f"orphan children: {parent_child.get('orphan_children', 0)}")

    bos = rule_stats.get("bos_direction")
    if bos:
        totals = bos.get("totals") or {}
        lines.append(f"- BOS direction — ranges UP/DOWN: {totals.get('range_bos_up', 0)}/"
                     f"{totals.get('range_bos_down', 0)}; events UP/DOWN: "
                     f"{totals.get('event_bos_up', 0)}/{totals.get('event_bos_down', 0)}")

    retracement = rule_stats.get("retracement")
    if retracement:
        lines.append(f"- Retracement — sequences: {retracement.get('sequences', 0)}; "
                     f"classes: {_counts_inline(retracement.get('class_counts'))}; "
                     f"avg percent: {retracement.get('avg_retracement_percent')}")

    reclaim = rule_stats.get("bos_reclaim")
    if reclaim:
        lines.append(f"- BOS reclaim — BOS pairs: {reclaim.get('bos_count', 0)}; "
                     f"reclaimed: {reclaim.get('reclaim_true', 0)}; "
                     f"not reclaimed: {reclaim.get('reclaim_false', 0)}; "
                     f"unresolved: {reclaim.get('unresolved', 0)}; "
                     f"depth classes: {_counts_inline(reclaim.get('class_counts'))}")

    abandon = rule_stats.get("bos_abandon")
    if abandon:
        lines.append(f"- BOS abandon — pairs: {abandon.get('pairs', 0)}; "
                     f"abandoned: {abandon.get('abandoned', 0)}; "
                     f"continued: {abandon.get('continued', 0)}; "
                     f"unresolved: {abandon.get('unresolved', 0)}; "
                     f"reasons: {_counts_inline(abandon.get('reason_counts'))}")

    rotation = rule_stats.get("rotation")
    if rotation:
        lines.append(f"- Extreme rotation — parents: {rotation.get('parents', 0)}; "
                     f"premium touches: {rotation.get('premium_touches', 0)}; "
                     f"discount touches: {rotation.get('discount_touches', 0)}; "
                     f"rotations: {rotation.get('rotations', 0)}")

    sequence = rule_stats.get("sequence")
    if sequence:
        lines.append(f"- Impulse/retest — chains: {sequence.get('chains', 0)}; "
                     f"impulses: {sequence.get('impulses', 0)}; "
                     f"max impulse index: {sequence.get('max_impulse_index')}; "
                     f"retests measured: {sequence.get('retests_measured', 0)}")

    outcomes = rule_stats.get("outcomes")
    if outcomes:
        lines.append(f"- Outcomes — pairs: {outcomes.get('pairs', 0)}; "
                     f"{_counts_inline(outcomes.get('counts'))}")

    if len(lines) == 2:
        lines.append("No rule model statistics produced.")
    lines.append("")
    return lines
