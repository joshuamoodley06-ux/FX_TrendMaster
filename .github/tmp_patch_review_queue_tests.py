from pathlib import Path

path = Path("python/range_library_memory/tests/test_structure_review_queue.py")
text = path.read_text(encoding="utf-8")
old = '''def imported_db(tmp_path: Path, ranges: list[dict]) -> Path:\n    db = tmp_path / "memory.sqlite3"\n    import_source(db, write_source(tmp_path, ranges), "fixture")\n    return db\n'''
new = '''def imported_db(tmp_path: Path, ranges: list[dict]) -> Path:\n    db = tmp_path / "memory.sqlite3"\n    import_source(db, write_source(tmp_path, ranges), "fixture")\n    # These tests add their own explicit duplicate candidate when needed.\n    # Ignore importer-generated overlap candidates so each fixture tests one root cause.\n    with sqlite3.connect(db) as connection:\n        connection.execute("UPDATE duplicate_candidates SET review_status='ignored'")\n    return db\n'''
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise SystemExit("Expected imported_db fixture block was not found")
path.write_text(text, encoding="utf-8")
