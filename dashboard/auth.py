from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from config.settings import settings

_security = HTTPBasic(auto_error=False)


def verify_auth(credentials: Annotated[HTTPBasicCredentials | None, Depends(_security)]) -> str:
    expected_user = settings.dashboard_username
    expected_pass = settings.dashboard_password

    if not expected_user or not expected_pass:
        return "anonymous"

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    user_ok = secrets.compare_digest(credentials.username.encode("utf8"), expected_user.encode("utf8"))
    pass_ok = secrets.compare_digest(credentials.password.encode("utf8"), expected_pass.encode("utf8"))

    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    return credentials.username
