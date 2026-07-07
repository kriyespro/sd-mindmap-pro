from __future__ import annotations

from django.shortcuts import redirect
from django.urls import reverse

from users.ui_mode import get_user_ui_mode, path_allowed_for_mode


class UIModeGuardMiddleware:
    """Redirect users away from nav areas hidden by their display mode."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and request.method == 'GET':
            path = request.path
            mode = get_user_ui_mode(user)
            if not path_allowed_for_mode(path, mode):
                return redirect(reverse('planner:board_personal'))
        return self.get_response(request)
