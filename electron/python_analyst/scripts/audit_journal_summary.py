"""One-off audit journal summary for workspace batches."""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

WORKSPACE = Path(r"C:\Users\joshu\OneDrive\Documents\FXTM_Analyst\workspace\XAUUSD")


def main() -> None:
    batches = sorted([d for d in WORKSPACE.iterdir() if d.is_dir()])
    all_codes: Counter[str] = Counter()
    batch_summaries: list[dict] = []

    for batch in batches:
        stats_path = batch / "yearly_stats.json"
        audit_path = batch / "reports" / "audit_warnings.csv"

        stats = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.exists() else {}
        counts = stats.get("counts", {})
        ranges = counts.get("ranges", 0)
        warnings_n = counts.get("warnings", 0)
        cases = counts.get("cases", 0)
        year = stats.get("year", "?")

        score = max(0, min(100, round(100 - (warnings_n / ranges) * 100))) if ranges else None

        codes: Counter[str] = Counter()
        by_code_samples: dict[str, list[dict]] = defaultdict(list)
        csv_rows = 0
        if audit_path.exists():
            with audit_path.open(encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    csv_rows += 1
                    code = row.get("code", "UNKNOWN")
                    codes[code] += 1
                    all_codes[code] += 1
                    if len(by_code_samples[code]) < 3:
                        by_code_samples[code].append(
                            {
                                "case": row.get("case_ref", ""),
                                "subject": row.get("subject_id", ""),
                                "msg": (row.get("message", "") or "")[:140],
                            }
                        )

        batch_summaries.append(
            {
                "batch": batch.name,
                "year": year,
                "ranges": ranges,
                "cases": cases,
                "warnings": warnings_n,
                "score": score,
                "codes": codes,
                "samples": dict(by_code_samples),
                "csv_rows": csv_rows,
            }
        )

    print("=" * 70)
    print("FXTM ANALYST AUDIT JOURNAL SUMMARY — XAUUSD")
    print("=" * 70)

    print("\n## BATCH OVERVIEW\n")
    print("| Batch | Stats year | Ranges | Cases | Warnings | Audit score |")
    print("|-------|------------|--------|-------|----------|-------------|")
    for b in batch_summaries:
        sc = f"{b['score']}%" if b["score"] is not None else "—"
        print(
            f"| {b['batch']} | {b['year']} | {b['ranges']} | {b['cases']} | {b['warnings']} | {sc} |"
        )

    print("\n## WARNING CODES (all batches combined)\n")
    for code, n in all_codes.most_common():
        print(f"  {code}: {n}")

    print("\n## PER-BATCH BREAKDOWN\n")
    for b in batch_summaries:
        print(f"\n### {b['batch']} (stats year={b['year']}, audit score={b['score']}%)")
        if not b["codes"]:
            print("  No warnings in audit_warnings.csv.")
            continue
        for code, n in b["codes"].most_common():
            print(f"  [{code}] ×{n}")
            for s in b["samples"].get(code, []):
                subj = s["subject"] or "—"
                case = s["case"] or "—"
                print(f"    • case={case}  range={subj}")
                print(f"      {s['msg']}")

    # summary.json warning breakdown if present
    print("\n## SUMMARY.JSON WARNING COUNTS (if available)\n")
    for batch in batches:
        summary_path = batch / "summary.json"
        if not summary_path.exists():
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        wc = summary.get("warning_counts") or summary.get("warnings_by_code")
        if wc:
            print(f"  {batch.name}: {wc}")

    total_ranges = sum(b["ranges"] for b in batch_summaries)
    total_warnings = sum(b["warnings"] for b in batch_summaries)
    print("\n## TOTALS")
    print(f"  Batches: {len(batch_summaries)}")
    print(f"  Total ranges (per-batch sum): {total_ranges}")
    print(f"  Total warnings (per-batch sum): {total_warnings}")


if __name__ == "__main__":
    main()
