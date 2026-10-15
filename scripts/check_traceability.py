import ast
import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
names = set()
for path in (root / "tests").glob("test_*.py"):
    names.update(
        n.name
        for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
e2e = (root / "frontend/demo-portal/e2e/reference.spec.ts").read_text(encoding="utf-8")
cases = (root / "docs/tests/cases.md").read_text(encoding="utf-8")
rows = list(csv.DictReader((root / "docs/tests/traceability.csv").open(encoding="utf-8")))
seen = set()
for row in rows:
    name = row["automated_test"]
    assert name in names or name in e2e, f"Unknown automated test: {name}"
    assert row["test_case"] in cases, f"Unknown test case: {row['test_case']}"
    assert row["test_case"] not in seen, f"Duplicate case: {row['test_case']}"
    seen.add(row["test_case"])
assert len(rows) >= 30
print(f"Traceability verified: {len(rows)} cases; all links resolve to real tests.")
