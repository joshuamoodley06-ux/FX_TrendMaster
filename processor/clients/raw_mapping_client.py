from __future__ import annotations

import requests


class RawMappingClient:
    def __init__(self, api_base: str) -> None:
        self.api_base = api_base.rstrip("/")

    def fetch_export(self, case_id: str) -> dict:
        url = f"{self.api_base}/api/v1/raw-mapping/events/export"
        response = requests.get(url, params={"case_id": case_id}, timeout=30)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError(f"Raw export failed: {payload}")
        return payload
