"""SQLite persistence bootstrap for Range Library Memory v1."""

from .config import DEFAULT_DB_PATH, ENV_DB_PATH, resolve_db_path
from .importer import import_source
from .schema import REQUIRED_TABLES, init_schema

# Register the independent sequential Weekly Script 1 v2 adapter before callers
# import the CLI. The approved v1 adapter remains untouched and version-scoped.
from . import doctrine_pipeline as _doctrine_pipeline
from . import weekly_chronology_bos as _weekly_chronology_bos
from .weekly_chronology_bos_v2_registry import install as _install_weekly_v2

_install_weekly_v2(_weekly_chronology_bos, _doctrine_pipeline)

__all__ = [
    "DEFAULT_DB_PATH",
    "ENV_DB_PATH",
    "REQUIRED_TABLES",
    "import_source",
    "init_schema",
    "resolve_db_path",
]
