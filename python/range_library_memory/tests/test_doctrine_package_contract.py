from __future__ import annotations

import pytest

from range_library_memory.doctrine_package_contract import (
    PACKAGE_ADAPTER,
    DoctrinePackageError,
    inspect_package,
)
from range_library_memory.tests.doctrine_package_test_support import package_source


def test_package_contract_is_validated_before_execution() -> None:
    valid = package_source("1", "v1")
    metadata = inspect_package(
        valid,
        expected_script_key="weekly_structure",
        expected_version_label="1",
        expected_execution_order=10,
    )
    assert metadata.adapter_key == PACKAGE_ADAPTER
    with pytest.raises(DoctrinePackageError, match="does not match"):
        inspect_package(valid, expected_version_label="2")
    with pytest.raises(DoctrinePackageError, match=r"run\(context\)"):
        inspect_package(valid.replace("def run(context):", "def evaluate(context):"))
