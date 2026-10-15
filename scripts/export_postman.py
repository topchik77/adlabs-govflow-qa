import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
items = []


def add(name, method, path, body=None, expected=200):
    request = {
        "method": method,
        "header": [{"key": "X-Correlation-ID", "value": "postman-reference"}],
        "url": "{{base_url}}" + path,
    }
    if body is not None:
        request["header"].append({"key": "Content-Type", "value": "application/json"})
        request["body"] = {"mode": "raw", "raw": body}
    items.append(
        {
            "name": name,
            "request": request,
            "event": [
                {
                    "listen": "test",
                    "script": {
                        "type": "text/javascript",
                        "exec": [
                            f"pm.test('HTTP {expected}', () => pm.response.to.have.status({expected}));"
                        ],
                    },
                }
            ],
        }
    )


def login(role, tenant="a"):
    add(
        f"Login {role}.{tenant}",
        "POST",
        "/auth/login",
        json.dumps({"username": f"{role}.{tenant}", "password": "{{password}}"}),
    )


login("applicant")
add(
    "Create draft",
    "POST",
    "/applications",
    json.dumps(
        {
            "type": "PERMIT",
            "title": "Postman synthetic permit",
            "description": "Synthetic information for local reference testing only.",
        }
    ),
    201,
)
add(
    "Upload synthetic PNG (select local file)",
    "POST",
    "/applications/{{application_id}}/attachments",
    expected=201,
)
items[-1]["request"]["body"] = {
    "mode": "formdata",
    "formdata": [
        {"key": "expected_version", "type": "text", "value": "{{version}}"},
        {"key": "file", "type": "file", "src": "synthetic.png"},
    ],
}
add(
    "Prepare signature",
    "POST",
    "/applications/{{application_id}}/prepare-signature",
    '{"expected_version":{{version}}}',
)
add(
    "Sign application (educational)",
    "POST",
    "/applications/{{application_id}}/sign",
    '{"expected_version":{{version}},"document_hash":"{{document_hash}}"}',
)
add("Submit", "POST", "/applications/{{application_id}}/submit", '{"expected_version":{{version}}}', 202)
items[-1]["request"]["header"].append({"key": "Idempotency-Key", "value": "postman-{{application_id}}"})
add("Get latest version (wait for UNDER_REVIEW)", "GET", "/applications/{{application_id}}")
login("reviewer")
add(
    "Approve with reason",
    "POST",
    "/applications/{{application_id}}/review",
    '{"expected_version":{{version}},"decision":"APPROVED",'
    '"reason":"Synthetic information verified by reviewer."}',
)
login("officer")
add(
    "Sign decision (educational)",
    "POST",
    "/applications/{{application_id}}/sign-decision",
    '{"expected_version":{{version}},"document_hash":"{{decision_hash}}"}',
)
add("Audit and correlation evidence", "GET", "/applications/{{application_id}}/audit")
login("applicant", "b")
add("Other tenant must get 404", "GET", "/applications/{{application_id}}", expected=404)
collection = {
    "info": {
        "name": "GovFlow Stage 1 reference",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "{{token}}", "type": "string"}]},
    "variable": [
        {"key": "base_url", "value": "http://127.0.0.1:8014/api/v1"},
        {"key": "password", "value": ""},
    ],
    "event": [
        {
            "listen": "test",
            "script": {
                "type": "text/javascript",
                "exec": [
                    "const j = pm.response.json();",
                    "if(j.access_token) pm.collectionVariables.set('token', j.access_token);",
                    "if(j.id && j.document_version) pm.collectionVariables.set('application_id', j.id);",
                    "if(j.version) pm.collectionVariables.set('version', j.version);",
                    "if(j.document_hash) pm.collectionVariables.set('document_hash', j.document_hash);",
                    "if(j.decision_hash) pm.collectionVariables.set('decision_hash', j.decision_hash);",
                ],
            },
        }
    ],
    "item": items,
}
target = root / "postman"
target.mkdir(exist_ok=True)
(target / "govflow.postman_collection.json").write_text(json.dumps(collection, indent=2), encoding="utf-8")
# A standard tiny PNG fixture; no real personal data or user uploads.
import base64  # noqa: E402

(target / "synthetic.png").write_bytes(
    base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jC1cAAAAASUVORK5CYII="
    )
)
print("Exported Postman collection with no stored credentials.")
