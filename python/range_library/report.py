from typing import List, Dict, Any

def generate_report(ranges: List[Any]) -> Dict[str, Any]:
    """Generates a summary report from normalized ranges or raw dicts."""
    report = {
        "total_ranges": len(ranges),
        "counts_by_layer": {},
        "counts_by_status": {},
        "orphan_count": 0
    }

    for r in ranges:
        # Handle both raw dict and RangeRecord object
        if hasattr(r, "layer"):
            layer = r.layer
            status = r.status
            parent_id = r.parent_id
        else:
            layer = r.get("structure_layer") or r.get("layer")
            status = r.get("status")
            parent_id = r.get("parent_range_id")

        if layer:
            report["counts_by_layer"][layer] = report["counts_by_layer"].get(layer, 0) + 1
        if status:
            report["counts_by_status"][status] = report["counts_by_status"].get(status, 0) + 1
        if not parent_id and layer != "MACRO":
            report["orphan_count"] += 1

    return report
