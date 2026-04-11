from __future__ import annotations

from typing import Any

from users.models import Profile


def account_profile(request: Any) -> dict[str, Any]:
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {}
    try:
        p = request.user.profile
    except Profile.DoesNotExist:
        return {}
    return {'account_profile': p}
