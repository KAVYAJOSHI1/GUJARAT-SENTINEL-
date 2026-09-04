"""
Role-based access control dependency factory.
Usage: `Depends(require_roles(UserRole.ADMIN, UserRole.OFFICER))`
"""
from fastapi import Depends, HTTPException, status

from app.api.deps import get_current_user
from app.models.base import UserRole
from app.schemas.auth import CurrentUser


def require_roles(*allowed_roles: UserRole):
    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FORBIDDEN",
                    "message": f"Role '{user.role}' is not permitted to perform this action.",
                },
            )
        return user

    return dependency
