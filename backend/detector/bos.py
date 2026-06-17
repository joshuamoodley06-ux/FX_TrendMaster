"""BOS detector — wick for HTF, body close for M15/Micro."""

from __future__ import annotations

from detector.break_rules import breaches_high, breaches_low
from detector.models import DetectionContext, SuggestionDraft
from detector.versions import BOS_V1


def detect_bos_suggestions(ctx: DetectionContext) -> list[SuggestionDraft]:
    if not ctx.has_range():
        return []
    active = ctx.active_candle
    if active is None:
        return []

    rh = float(ctx.range_high)  # type: ignore[arg-type]
    rl = float(ctx.range_low)  # type: ignore[arg-type]
    rule = ctx.break_rule
    tf = ctx.tf_prefix
    drafts: list[SuggestionDraft] = []
    idx = 0

    if breaches_high(active.high, active.close, rh, rule):
        drafts.append(
            SuggestionDraft(
                candidate_kind="BOS_UP",
                detector_version=BOS_V1,
                candle_index=active.index,
                candle_time_utc_ms=active.time_ms,
                candidate_index=idx,
                movement_rule="STRUCTURE_BOS_UP",
                derived_event_code=f"{tf}_BOS_UP",
                primitive="BREACH",
                break_rule=rule,
                event_side="UP",
                event_price=active.close if rule == "BODY_CLOSE" else active.high,
                confidence="HIGH",
                reason_text=f"BOS UP: {rule} broke range high {rh:.2f}",
                meta_json={"range_high": rh, "range_low": rl, "break_rule": rule},
            )
        )
        idx += 1

    if breaches_low(active.low, active.close, rl, rule):
        drafts.append(
            SuggestionDraft(
                candidate_kind="BOS_DOWN",
                detector_version=BOS_V1,
                candle_index=active.index,
                candle_time_utc_ms=active.time_ms,
                candidate_index=idx,
                movement_rule="STRUCTURE_BOS_DOWN",
                derived_event_code=f"{tf}_BOS_DOWN",
                primitive="BREACH",
                break_rule=rule,
                event_side="DOWN",
                event_price=active.close if rule == "BODY_CLOSE" else active.low,
                confidence="HIGH",
                reason_text=f"BOS DOWN: {rule} broke range low {rl:.2f}",
                meta_json={"range_high": rh, "range_low": rl, "break_rule": rule},
            )
        )

    return drafts
