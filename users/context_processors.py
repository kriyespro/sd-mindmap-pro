from __future__ import annotations

from typing import Any

from users.models import Profile
from users.ui_mode import chrome_for_mode, get_user_ui_mode


def account_profile(request: Any) -> dict[str, Any]:
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {'ui': chrome_for_mode(Profile.UI_MODE_PRO)}
    try:
        p = request.user.profile
    except Profile.DoesNotExist:
        mode = Profile.UI_MODE_PRO
        return {
            'ui': chrome_for_mode(mode),
            'ui_mode': mode,
        }
    mode = get_user_ui_mode(request.user)
    return {
        'account_profile': p,
        'ui_mode': mode,
        'ui': chrome_for_mode(mode),
    }
