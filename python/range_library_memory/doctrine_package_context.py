"""Read-only evidence context exposed to an FXTM doctrine package."""
from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
from typing import Any, Mapping

from .doctrine_package_contract import CONTEXT_CONTRACT, stable_json
from .source_market_db import latest_candle_time, load_candles, open_source_market_db


def _matches_case(node: Mapping[str, Any], case_ref: str) -> bool:
    refs = node.get("source_refs")
    return isinstance(refs, list) and any(
        isinstance(ref, Mapping) and str(ref.get("case_ref") or "") == case_ref
        for ref in refs
    )


def _walk_ranges(root: Any, case_ref: str) -> list[dict[str, Any]]:
    if not isinstance(root, Mapping):
        return []
    result: list[dict[str, Any]] = []
    stack: list[Mapping[str, Any]] = [root]
    unlinked = root.get("unlinked_review_children")
    if isinstance(unlinked, list):
        stack.extend(item for item in unlinked if isinstance(item, Mapping))
    while stack:
        node = stack.pop()
        if str(node.get("node_type") or "").upper() == "RANGE" and _matches_case(node, case_ref):
            result.append(json.loads(stable_json(node)))
        children = node.get("children")
        if isinstance(children, list):
            stack.extend(child for child in reversed(children) if isinstance(child, Mapping))
    return result


def _ranges(master: Mapping[str, Any], case_ref: str) -> list[dict[str, Any]]:
    return _walk_ranges(master.get("trusted_root"), case_ref)


def _review_ranges(master: Mapping[str, Any], case_ref: str) -> list[dict[str, Any]]:
    return _walk_ranges(master.get("review_root"), case_ref)


class DoctrinePackageContext:
    """Narrow structural memory and candle API. No writable DB handle is exposed."""

    def __init__(
        self,
        *,
        master_map: Mapping[str, Any],
        source_db: str | Path,
        case_ref: str,
        symbol: str,
        structural_content_hash: str,
    ) -> None:
        self.contract = CONTEXT_CONTRACT
        self.case_ref = str(case_ref)
        self.symbol = str(symbol).upper()
        self.structural_content_hash = str(structural_content_hash)
        self.__source_db = Path(source_db).resolve()
        self.__ranges = tuple(_ranges(master_map, self.case_ref))
        self.__review_ranges = tuple(_review_ranges(master_map, self.case_ref))
        self.__index = {str(item.get("id") or ""): item for item in self.__ranges}

    def selected_ranges(self, *, layer: str | None = None) -> tuple[dict[str, Any], ...]:
        layer_key = str(layer or "").upper()
        rows = self.__ranges if not layer_key else tuple(
            item for item in self.__ranges
            if str(item.get("structure_layer") or item.get("layer") or "").upper() == layer_key
        )
        return tuple(json.loads(stable_json(item)) for item in rows)

    def review_ranges(self, *, layer: str | None = None) -> tuple[dict[str, Any], ...]:
        """Return review-only structural evidence without making it statistics-eligible."""
        layer_key = str(layer or "").upper()
        rows = self.__review_ranges if not layer_key else tuple(
            item for item in self.__review_ranges
            if str(item.get("structure_layer") or item.get("layer") or "").upper() == layer_key
        )
        return tuple(json.loads(stable_json(item)) for item in rows)

    def approved_memory(self, canonical_range_id: str) -> dict[str, Any]:
        node = self.__index.get(str(canonical_range_id)) or {}
        memory = node.get("analysis_enrichments")
        return json.loads(stable_json(memory)) if isinstance(memory, Mapping) else {}

    def latest_candle_time(self, timeframe: str) -> str | None:
        with closing(open_source_market_db(self.__source_db, required_tables=("candles",))) as source:
            return latest_candle_time(
                source, symbol=self.symbol, timeframe=str(timeframe).upper()
            )

    def load_candles(
        self, *, timeframe: str, start_time: str, end_time: str
    ) -> tuple[dict[str, Any], ...]:
        with closing(open_source_market_db(self.__source_db, required_tables=("candles",))) as source:
            candles = load_candles(
                source,
                symbol=self.symbol,
                timeframe=str(timeframe).upper(),
                start_time=str(start_time),
                end_time=str(end_time),
            )
        return tuple({
            "time": candle.time, "open": candle.open, "high": candle.high,
            "low": candle.low, "close": candle.close,
            "volume": getattr(candle, "volume", None),
            "source": getattr(candle, "source", None),
        } for candle in candles)
