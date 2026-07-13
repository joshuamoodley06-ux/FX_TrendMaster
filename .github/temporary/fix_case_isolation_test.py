from pathlib import Path

path = Path("python/range_library_memory/tests/test_structure_review_queue.py")
text = path.read_text(encoding="utf-8")
old = "WHERE review_key='parent:428'"
new = "WHERE review_key='parent:case:one:428'"
if text.count(old) != 1:
    raise RuntimeError(f"Expected one legacy review-key assertion, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
