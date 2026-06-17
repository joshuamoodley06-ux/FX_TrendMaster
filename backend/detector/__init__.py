"""Python Detector V1 — current-timeframe deterministic OHLC detectors.

Outputs suggestions only via detection_brain_store. Never writes confirmed structure.
"""

from detector.pipeline import DetectionResult, run_detector_v1
from detector.writer import write_suggestions

__all__ = ["DetectionResult", "run_detector_v1", "write_suggestions"]
