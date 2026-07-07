from __future__ import annotations

from typing import Any

from users.models import Profile

ALL_LAYOUTS = ('tree', 'mindmap', 'mini', 'idea', 'kanban')

LAYOUTS_BY_MODE: dict[str, tuple[str, ...]] = {
    Profile.UI_MODE_MINIMAL: ('tree', 'mindmap'),
    Profile.UI_MODE_EXPRESS: ('tree', 'mindmap', 'kanban'),
    Profile.UI_MODE_PRO: ALL_LAYOUTS,
}

SIDEBAR_BY_MODE: dict[str, dict[str, bool]] = {
    Profile.UI_MODE_MINIMAL: {
        'projects': False,
        'archived_projects': False,
        'gantt': False,
        'milestones': False,
        'calendar': False,
        'time_tracking': False,
        'reports': False,
        'resources': False,
    },
    Profile.UI_MODE_EXPRESS: {
        'projects': True,
        'archived_projects': False,
        'gantt': True,
        'milestones': False,
        'calendar': False,
        'time_tracking': False,
        'reports': False,
        'resources': False,
    },
    Profile.UI_MODE_PRO: {
        'projects': True,
        'archived_projects': True,
        'gantt': True,
        'milestones': True,
        'calendar': True,
        'time_tracking': True,
        'reports': True,
        'resources': True,
    },
}

TOPBAR_BY_MODE: dict[str, dict[str, bool]] = {
    Profile.UI_MODE_MINIMAL: {
        'gantt': False,
        'import_export': False,
    },
    Profile.UI_MODE_EXPRESS: {
        'gantt': True,
        'import_export': True,
    },
    Profile.UI_MODE_PRO: {
        'gantt': True,
        'import_export': True,
    },
}

PATH_SIDEBAR_FEATURE: tuple[tuple[str, str], ...] = (
    ('/projects/archived', 'archived_projects'),
    ('/projects/', 'projects'),
    ('/gantt/', 'gantt'),
    ('/milestones/', 'milestones'),
    ('/calendar/', 'calendar'),
    ('/time/', 'time_tracking'),
    ('/reports/', 'reports'),
    ('/resources/', 'resources'),
)


def get_user_ui_mode(user) -> str:
    if user is None or not getattr(user, 'is_authenticated', False):
        return Profile.UI_MODE_PRO
    try:
        mode = user.profile.ui_mode
    except Profile.DoesNotExist:
        return Profile.UI_MODE_PRO
    if mode not in LAYOUTS_BY_MODE:
        return Profile.UI_MODE_PRO
    return mode


def chrome_for_mode(mode: str) -> dict[str, Any]:
    if mode not in LAYOUTS_BY_MODE:
        mode = Profile.UI_MODE_PRO
    labels = dict(Profile.UI_MODE_CHOICES)
    return {
        'mode': mode,
        'label': labels.get(mode, 'Pro'),
        'layouts': list(LAYOUTS_BY_MODE[mode]),
        'sidebar': dict(SIDEBAR_BY_MODE[mode]),
        'top': dict(TOPBAR_BY_MODE[mode]),
    }


def normalize_layout(mode: str, layout: str) -> str:
    allowed = LAYOUTS_BY_MODE.get(mode, LAYOUTS_BY_MODE[Profile.UI_MODE_PRO])
    if layout in allowed:
        return layout
    return allowed[0]


def sidebar_feature_for_path(path: str) -> str | None:
    for prefix, feature in PATH_SIDEBAR_FEATURE:
        if path.startswith(prefix):
            return feature
    return None


def path_allowed_for_mode(path: str, mode: str) -> bool:
    if path.startswith('/billing/'):
        return True
    feature = sidebar_feature_for_path(path)
    if feature is None:
        return True
    chrome = chrome_for_mode(mode)
    return bool(chrome['sidebar'].get(feature, False))
