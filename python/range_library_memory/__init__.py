"""SQLite persistence bootstrap for Range Library Memory v1."""

from .config import DEFAULT_DB_PATH, ENV_DB_PATH, resolve_db_path
from .importer import import_source
from .schema import REQUIRED_TABLES, init_schema

# Legacy Weekly adapters remain registered only so existing analysis workspaces
# can still be opened. New Weekly knowledge enters the active Python brain as
# ordinary doctrine packages after five-sample approval.
from . import doctrine_pipeline as _doctrine_pipeline
from . import weekly_chronology_bos as _weekly_chronology_bos
from .daily_inherited_doctrine import install as _install_daily_inherited_doctrine
from .doctrine_package_runtime_registry import install as _install_doctrine_packages
from .weekly_chronology_bos_v2_registry import install as _install_weekly_v2

_install_weekly_v2(_weekly_chronology_bos, _doctrine_pipeline)
_install_doctrine_packages(_doctrine_pipeline)
_install_daily_inherited_doctrine(_doctrine_pipeline)

__all__ = [
    "DEFAULT_DB_PATH",
    "ENV_DB_PATH",
    "REQUIRED_TABLES",
    "import_source",
    "init_schema",
    "resolve_db_path",
]
