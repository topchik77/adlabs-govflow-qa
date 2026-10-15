"""Generate local-only secrets; never print passwords/tokens."""

import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / ".env"
if target.exists():
    print(".env already exists; kept current configuration.")
else:
    target.write_text(
        "DATABASE_URL=postgresql+psycopg://govflow:govflow-local@127.0.0.1:55434/govflow\n"
        f"JWT_SECRET={secrets.token_hex(32)}\nSIGNATURE_SECRET={secrets.token_hex(32)}\n"
        f"DEMO_PASSWORD={secrets.token_urlsafe(18)}\nSEED=42\n",
        encoding="utf-8",
    )
    print("Created .env with random local credentials. Read DEMO_PASSWORD there to sign in.")
