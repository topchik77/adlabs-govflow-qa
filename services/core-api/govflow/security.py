import uuid
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

passwords = PasswordHash.recommended()
DUMMY_HASH = passwords.hash("unused-timing-equalization")


def issue_token(user, secret):
    return jwt.encode(
        {
            "sub": user.id,
            "tenant_id": user.tenant_id,
            "role": user.role,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=60),
            "iat": datetime.now(timezone.utc),
            "jti": str(uuid.uuid4()),
            "iss": "govflow-lab",
        },
        secret,
        algorithm="HS256",
    )


def read_token(token, secret):
    return jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        issuer="govflow-lab",
        options={"require": ["sub", "tenant_id", "role", "exp", "jti", "iss"]},
    )
