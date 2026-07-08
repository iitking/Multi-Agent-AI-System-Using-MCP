"""Authentication and authorization dependencies for FastAPI endpoints."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from backend.config import get_settings
from backend.security.permissions import has_permission

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_auth = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthUser:
    username: str
    role: str
    api_key: str


def get_current_user(
    api_key_val: str | None = Security(api_key_header),
    bearer_val: HTTPAuthorizationCredentials | None = Security(bearer_auth),
) -> AuthUser:
    """Authenticate via X-API-Key or Bearer token header."""
    key = api_key_val or (bearer_val.credentials if bearer_val else None)
    if not key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide via 'X-API-Key' header or 'Authorization: Bearer <key>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_settings()
    user_info = settings.api_keys.get(key)
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username, role = user_info
    return AuthUser(username=username, role=role, api_key=key)


def require_permission(permission: str) -> Callable[[AuthUser], AuthUser]:
    """Dependency factory checking whether the authenticated user's role has permission."""
    def dependency(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if not has_permission(user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' lacks required permission: '{permission}'.",
            )
        return user

    return dependency
