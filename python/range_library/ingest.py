import json
from typing import List, Dict, Any

def load_ranges_from_json(path: str) -> List[Dict[str, Any]]:
    with open(path, "r") as f:
        data = json.load(f)
    return data.get("ranges", [])
