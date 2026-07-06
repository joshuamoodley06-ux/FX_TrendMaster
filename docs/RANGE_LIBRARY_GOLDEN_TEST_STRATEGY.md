# Investigation Report: Range Library Golden Test Strategy

## 1. Branch and Package Status
- **Branch Mismatch**: The current branch `fix/daily-boundary-edit-parent-warning` (and other checked branches) does **not** contain the `python/range_library/` directory or the reference export file `current_mapping_XAUUSD_raw_20f4eeba-94e7-4d06-806e-2fa2aa15ec74.json`.
- **Existing Paths**: `processor/` and `electron/python_analyst/` appear to be separate processing or legacy analytical systems. They should not be used as the target for the Range Library v0.1 fixture unless the Range Library branch intentionally unified them.
- **Assumed Package State**: Based on the Codex report, the library is structured as a standard Python package with dedicated modules for `ingest`, `normalize`, `validate`, and `report`.

## 2. Recommended Fixture Strategy
- **Fixture Path**: `python/range_library/tests/fixtures/current_mapping_XAUUSD_raw_20f4eeba-94e7-4d06-806e-2fa2aa15ec74.json`
- **Strategy**: Use the **Full Real Export** as the primary "Golden Fixture". This ensures the library is tested against the actual complexity, scale, and potential edge-case errors of the TradingView mapping tool.

## 3. Golden Test Assertions
The test should load the real export and assert the following metrics to "lock" the contract:
- **Ingestion**: `library.load(fixture_path)` must complete without raising exceptions.
- **Range Count**: `len(library.ranges)` must match the number of range objects in the source JSON.
- **Layer distribution**: Assert specific counts for `MACRO`, `WEEKLY`, `DAILY`, and `INTRADAY` (based on XAUUSD case stats).
- **Status Counts**: Assert counts for `ACTIVE` vs `BROKEN` ranges.
- **Hierarchy**: Verify `orphan_count` is 0 (or a specific known number).
- **Chains**: Verify that `next_range_id` links correctly reconstruct at least one known temporal sequence.
- **Validation**: Assert that `library.validate()` identifies known issues (e.g., missing parent for an Intraday range) but **does not mutate** the underlying `RangeRecord` data.

## 4. CLI and Environment
- **Execution from root**:
  ```bash
  PYTHONPATH=python python -m range_library.cli \
    --export python/range_library/tests/fixtures/current_mapping_XAUUSD_raw_20f4eeba-94e7-4d06-806e-2fa2aa15ec74.json \
    --report-json reports/xauusd_golden_report.json
  ```
- **Requirements**: Ensure `PYTHONPATH` includes the `python/` directory to allow absolute imports within the package.

## 5. Codex Implementation Task (Recommended)
Once the correct branch is available, Codex should perform the following:
1.  **Add Fixture**: Place the reference JSON in `python/range_library/tests/fixtures/`.
2.  **Create Test**: Create `python/range_library/tests/test_golden_report.py`.
3.  **Implement `test_golden_report_consistency`**:
    - Load the fixture.
    - Run the normalization and validation pipeline.
    - Compare the resulting `RangeLibraryReport` against a hardcoded or JSON-based baseline of expected counts and metrics.
4.  **CLI Verification**: Update `cli.py` to ensure the `--report-json` flag produces a structured output compatible with the golden test assertions.

## 6. Risks and Notes
- **Price Precision**: Ensure normalization uses `Decimal` for price fields to prevent assertion failures due to floating-point drift.
- **ID Stability**: Confirm if `range_id` is always present or if the library falls back to a generated hash; the golden test must rely on stable identifiers.
- **Immutability**: The test must verify that `RangeRecord` objects remain `frozen` throughout the validation pass.
