import json
import argparse
from range_library.ingest import load_ranges_from_json
from range_library.normalize import normalize_range
from range_library.report import generate_report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--json-out", required=True)
    args = parser.parse_args()

    raw_ranges = load_ranges_from_json(args.input)
    normalized = [normalize_range(r) for r in raw_ranges]
    report = generate_report(normalized)

    with open(args.json_out, "w") as f:
        json.dump(report, f, indent=2)

    print(f"Exited 0 and wrote {args.json_out}")

if __name__ == "__main__":
    main()
