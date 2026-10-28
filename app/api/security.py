"""Access control for the deployed service.

The screen handles health data, so it must not sit open on a public address.
Credentials come from the environment: with none set the service stays open and
says so in the log, which is what local development wants.
"""
from __future__ import annotations

import logging
import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

logger = logging.getLogger(__name__)
scheme = HTTPBasic(auto_error=False)


def expected_credentials() -> tuple[str, str] | None:
    user = os.getenv("AUTH_USER")
    password = os.getenv("AUTH_PASSWORD")
    return (user, password) if user and password else None


def require_access(credentials: HTTPBasicCredentials | None = Depends(scheme)) -> str:
    expected = expected_credentials()
    if expected is None:
        return "aberto"

    user, password = expected
    if credentials is None or not (
        secrets.compare_digest(credentials.username, user)
        and secrets.compare_digest(credentials.password, password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="acesso restrito",
            # cabeçalho HTTP não carrega acento: o realm vai sem ele
            headers={"WWW-Authenticate": 'Basic realm="Conferencia de guias"'},
        )
    return credentials.username


def warn_if_open() -> None:
    if expected_credentials() is None:
        logger.warning(
            "serviço sem autenticação: defina AUTH_USER e AUTH_PASSWORD antes de expor em rede"
        )
