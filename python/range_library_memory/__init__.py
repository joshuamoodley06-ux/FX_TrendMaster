"""SQLite persistence bootstrap for Range Library Memory v1."""

from .config import DEFAULT_DB_PATH, ENV_DB_PATH, resolve_db_path
from .importer import import_source
from .schema import REQUIRED_TABLES, init_schema

# Install the explicit sequential Weekly Script 1 v2 policy before callers
# import the CLI or doctrine pipeline. This mirrors the established Master Map
# lifecycle installer pattern while preserving the base persistence contract.
from . import doctrine_pipeline as _doctrine_pipeline
from . import weekly_chronology_bos as _weekly_chronology_bos
from .weekly_chronology_bos_sequence import install as _install_weekly_sequence

_install_weekly_sequence(_weekly_chronology_bos, _doctrine_pipeline)

__all__ = [
    "DEFAULT_DB_PATH",
    "ENV_DB_PATH",
    "REQUIRED_TABLES",
    "import_source",
    "init_schema",
    "resolve_db_path",
]
