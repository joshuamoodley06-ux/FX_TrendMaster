from __future__ import annotations

import argparse
import sys

from processor.audits.audit_report import assert_schema_version, build_audit_report
from processor.clients.raw_mapping_client import RawMappingClient
from processor.config import ProcessorConfig
from processor.core.ledger_hash import compute_ledger_hash
from processor.core.ledger_resolver import resolve_ledger
from processor.storage.export_writer import write_audit_json


def main() -> int:
    parser = argparse.ArgumentParser(description="FX TrendMaster raw mapping processor")
    parser.add_argument("--case-id", required=True, help="Raw mapping case_id from the VPS ledger")
    args = parser.parse_args()

    config = ProcessorConfig()
    client = RawMappingClient(config.api_base)
    export = client.fetch_export(args.case_id)

    meta = export.get("meta") or {}
    assert_schema_version(meta)

    sequence_by_intent = export.get("sequence_by_intent") or []
    backend_ledger_hash = str(meta.get("ledger_hash") or "")
    local_ledger_hash = compute_ledger_hash(sequence_by_intent)

    if backend_ledger_hash != local_ledger_hash:
        print("Ledger hash mismatch between backend export and local recompute.", file=sys.stderr)
        print(f"Backend ledger hash: {backend_ledger_hash}", file=sys.stderr)
        print(f"Local ledger hash:   {local_ledger_hash}", file=sys.stderr)
        return 1

    resolve_result = resolve_ledger(export)
    audit = build_audit_report(
        export,
        resolve_result,
        backend_ledger_hash=backend_ledger_hash,
        local_ledger_hash=local_ledger_hash,
    )
    audit_path = write_audit_json(audit, config.export_dir, args.case_id)

    print(f"Fetched case: {meta.get('case_id')}")
    print(f"Schema version: {meta.get('schema_version')}")
    print(f"Backend ledger hash: {backend_ledger_hash}")
    print(f"Local ledger hash: {local_ledger_hash}")
    print(f"Raw record count: {resolve_result.raw_record_count}")
    print(f"Visible/surviving record count: {resolve_result.visible_record_count}")
    print(f"Delete record count: {resolve_result.delete_record_count}")
    print(f"Audit JSON path: {audit_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
