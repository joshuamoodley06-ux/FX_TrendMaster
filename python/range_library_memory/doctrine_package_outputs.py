"""Normalize derived outputs returned by an FXTM doctrine package."""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from .doctrine_package_context import DoctrinePackageContext
from .doctrine_package_contract import (
    ALLOWED_PROCESSING_STATUSES,
    DoctrinePackageError,
    content_sha,
    stable_json,
)


def validate_outputs(
    value: Any,
    *,
    context: DoctrinePackageContext,
    package_hash: str,
) -> list[dict[str, Any]]:
    outputs = value.get("outputs") if isinstance(value, Mapping) else value
    if not isinstance(outputs, Sequence) or isinstance(outputs, (str, bytes, bytearray)):
        raise DoctrinePackageError("Package result must contain an outputs list.")

    eligible = {str(item.get("id") or "") for item in context.selected_ranges()}
    if not eligible:
        raise DoctrinePackageError("Selected case contains no trusted canonical ranges.")

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(outputs):
        if not isinstance(raw, Mapping):
            raise DoctrinePackageError(f"Output {index} must be an object.")
        canonical_id = str(raw.get("canonical_range_id") or "").strip()
        if not canonical_id or canonical_id not in eligible:
            raise DoctrinePackageError(f"Output {index} targets an ineligible range.")
        if canonical_id in seen:
            raise DoctrinePackageError(f"Duplicate output for {canonical_id}.")
        seen.add(canonical_id)

        status = str(raw.get("processing_status") or "").upper()
        if status not in ALLOWED_PROCESSING_STATUSES:
            raise DoctrinePackageError(f"Invalid status for {canonical_id}.")
        payload = raw.get("payload")
        if not isinstance(payload, Mapping):
            raise DoctrinePackageError(f"Payload for {canonical_id} must be an object.")

        safe_payload = json.loads(stable_json(payload))
        input_hash = str(
            raw.get("input_hash")
            or content_sha([context.structural_content_hash, canonical_id])
        )
        output_hash = content_sha({
            "package_content_hash": package_hash,
            "canonical_range_id": canonical_id,
            "processing_status": status,
            "payload": safe_payload,
        })
        result.append({
            "canonical_range_id": canonical_id,
            "input_hash": input_hash,
            "processing_status": status,
            "payload": safe_payload,
            "output_hash": output_hash,
        })

    if not result:
        raise DoctrinePackageError("Package returned no outputs.")
    return sorted(result, key=lambda item: item["canonical_range_id"])
