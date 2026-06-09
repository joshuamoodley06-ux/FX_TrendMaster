import argparse
from config import ProcessorConfig
from clients.raw_mapping_client import RawMappingClient
from core.ledger_resolver import resolve_ledger


def main() -> None:
    parser = argparse.ArgumentParser(description="FX TrendMaster raw mapping processor")
    parser.add_argument("--case-id", required=True, help="Raw mapping case_id from the VPS ledger")
    args = parser.parse_args()

    config = ProcessorConfig()
    client = RawMappingClient(config.api_base)
    export = client.fetch_export(args.case_id)
    result = resolve_ledger(export)

    meta = export.get("meta", {})
    print(f"Fetched case: {meta.get('case_id')}")
    print(f"Schema: {meta.get('schema_version')}")
    print(f"Ledger hash: {meta.get('ledger_hash')}")
    print(f"Raw records: {meta.get('total_records')}")
    print(f"Visible records: {len(result.visible_events)}")
    print(f"Warnings: {len(result.warnings)}")


if __name__ == "__main__":
    main()
