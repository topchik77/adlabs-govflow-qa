import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "services/core-api"))
from govflow.api import create_app  # noqa: E402

# Export requires no network, database or real signing secrets.
app = create_app(
    database_url="postgresql+psycopg://unused:unused@localhost/unused",
    jwt_secret="schema-export-only-" * 3,
    signature_secret="schema-export-only-" * 3,
)
(root / "docs/openapi.json").write_text(
    json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf-8"
)
print("Exported docs/openapi.json")
