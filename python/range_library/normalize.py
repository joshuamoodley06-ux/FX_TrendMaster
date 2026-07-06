from range_library.models import RangeRecord

def normalize_range(raw: dict) -> RangeRecord:
    return RangeRecord(
        range_id=str(raw.get("range_id") or raw.get("id", "")),
        layer=raw.get("structure_layer") or raw.get("layer", "UNKNOWN"),
        status=raw.get("status", "UNKNOWN"),
        parent_id=str(raw.get("parent_range_id")) if raw.get("parent_range_id") else None,
        active_from_time=raw.get("active_from_time"),
        inactive_from_time=raw.get("inactive_from_time"),
        raw=raw
    )
