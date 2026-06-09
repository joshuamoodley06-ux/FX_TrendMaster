from dataclasses import dataclass
import os


@dataclass(frozen=True)
class ProcessorConfig:
    api_base: str = os.getenv("FXTM_API_BASE", "https://api01.apexcoastalrentals.co.za")
    export_dir: str = os.getenv("FXTM_PROCESSOR_EXPORT_DIR", "exports")
