from __future__ import annotations

import csv
import io
import re
from datetime import date

from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet

from planner.crypto import decrypt_task_title
from planner.models import Notification, Task
from teams.models import Team, TeamMembership

User = get_user_model()


def _parse_iso_date(raw: str) -> date | None:
    value = (raw or '').strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _create_task(
    *,
    author: User,
    team: Team | None,
    title: str,
    parent: Task | None,
    due_date: date | None = None,
    assignee_username: str = '',
    project=None,
    position: int = 0,
) -> Task:
    return Task.objects.create(
        author=author,
        team=team,
        project=project,
        parent=parent,
        title=title.strip(),
        due_date=due_date,
        assignee_username=(assignee_username or '').strip(),
        position=position,
    )


def create_99d_template(
    *,
    author: User,
    team: Team | None = None,
    project=None,
    due_date: date | None = None,
    assignee_username: str = '',
    root_title: str = '',
) -> Task:
    """
    Create the 99D starter tree (4 levels):
    1×99D → 3×33D → each with 3×11D → each with 11×1D.
    Badges show depth; titles stay empty for the user to fill.
    """
    title = (root_title or '').strip()
    # Avoid duplicating badge labels as titles (UI already shows 99D / 33D / 11D / 1D).
    if title in {'99D', '33D', '11D', '1D'}:
        title = ''
    root = _create_task(
        author=author,
        team=team,
        project=project,
        title=title,
        parent=None,
        due_date=due_date,
        assignee_username=assignee_username,
        position=0,
    )
    for i in range(3):
        mid = _create_task(
            author=author,
            team=team,
            project=project,
            title='',
            parent=root,
            position=i,
        )
        for j in range(3):
            leaf_11 = _create_task(
                author=author,
                team=team,
                project=project,
                title='',
                parent=mid,
                position=j,
            )
            for k in range(11):
                _create_task(
                    author=author,
                    team=team,
                    project=project,
                    title='',
                    parent=leaf_11,
                    position=k,
                )
    return root


def import_tasks_from_upload(*, uploaded_file, author: User, team: Team | None) -> int:
    name = (uploaded_file.name or '').lower()
    try:
        raw_text = uploaded_file.read().decode('utf-8-sig')
    except UnicodeDecodeError as e:
        raise ValueError('File must be UTF-8 encoded') from e

    created = 0
    if name.endswith('.csv'):
        stream = io.StringIO(raw_text)
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError('CSV header missing')
        headers = {h.strip().lower() for h in reader.fieldnames if h}
        by_title: dict[str, Task] = {}
        title_mode = 'title' in headers
        task_mode = 'task' in headers
        if not (title_mode or task_mode):
            raise ValueError('CSV must include "title" or "task" column')

        for row in reader:
            row_lc = {(k or '').strip().lower(): (v or '').strip() for k, v in row.items()}
            if title_mode:
                title = row_lc.get('title', '')
                if not title:
                    continue
                parent_key = row_lc.get('parent', '') or row_lc.get('parent_title', '')
                parent = by_title.get(parent_key.lower()) if parent_key else None
                task = _create_task(
                    author=author,
                    team=team,
                    title=title,
                    parent=parent,
                    due_date=_parse_iso_date(row_lc.get('due_date', '')),
                    assignee_username=row_lc.get('assignee_username', ''),
                )
                created += 1
                by_title.setdefault(title.lower(), task)
                continue

            root_title = row_lc.get('task', '')
            sub_title = row_lc.get('subtask', '')
            if not root_title:
                continue
            root_key = root_title.lower()
            root = by_title.get(root_key)
            if root is None:
                root = _create_task(author=author, team=team, title=root_title, parent=None)
                by_title[root_key] = root
                created += 1
            if sub_title:
                _create_task(author=author, team=team, title=sub_title, parent=root)
                created += 1

    elif name.endswith('.txt'):
        lines = raw_text.splitlines()
        stack: list[tuple[int, Task]] = []
        for raw in lines:
            if not raw.strip():
                continue
            spaces = len(raw) - len(raw.lstrip(' \t'))
            level = max(0, spaces // 2)
            title = re.sub(r'^\s*([\-*•]|\d+\.)\s*', '', raw).strip()
            if not title:
                continue
            while stack and stack[-1][0] >= level:
                stack.pop()
            parent = stack[-1][1] if stack else None
            task = _create_task(author=author, team=team, title=title, parent=parent)
            stack.append((level, task))
            created += 1
    else:
        raise ValueError('Upload a .csv or .txt file')

    if created == 0:
        raise ValueError('No valid tasks found in file')
    return created


def count_all_descendants(node: dict) -> tuple[int, int]:
    total, done = 0, 0
    for child in node.get('children', []):
        total += 1
        if child['is_completed']:
            done += 1
        ct, cd = count_all_descendants(child)
        total += ct
        done += cd
    return total, done


def build_task_tree(tasks: list[dict], parent_id: int | None = None) -> list[dict]:
    by_parent: dict[int | None, list[dict]] = {}
    for task in tasks:
        by_parent.setdefault(task['parent_id'], []).append(task)

    def build(pid: int | None) -> list[dict]:
        siblings = by_parent.get(pid, [])
        siblings.sort(key=lambda t: t['id'], reverse=(pid is None))
        tree: list[dict] = []
        for task in siblings:
            node = dict(task)
            node['due_state'] = 'none'
            if node.get('due_date'):
                due = node['due_date']
                if hasattr(due, 'isoformat'):
                    d = due
                else:
                    try:
                        from datetime import datetime

                        d = datetime.strptime(str(due), '%Y-%m-%d').date()
                    except ValueError:
                        d = None
                if d:
                    today = date.today()
                    if d < today:
                        node['due_state'] = 'overdue'
                    elif d == today:
                        node['due_state'] = 'today'
                    else:
                        node['due_state'] = 'upcoming'
            node['children'] = build(task['id'])
            sub_total, sub_done = count_all_descendants(node)
            node['subtask_total'] = sub_total
            node['subtask_done'] = sub_done
            node['percent'] = (
                round((sub_done / sub_total) * 100)
                if sub_total > 0
                else (100 if node['is_completed'] else 0)
            )
            tree.append(node)
        return tree

    return build(parent_id)


def personal_visible_task_ids(user: User) -> set[int]:
    """Same rules as the Flask app: author or assignee, plus descendants and ancestors (personal tasks only)."""
    base_qs = Task.objects.filter(team__isnull=True)
    base_ids = set(
        base_qs.filter(Q(author=user) | Q(assignee_username=user.username)).values_list(
            'id', flat=True
        )
    )
    if not base_ids:
        return set()

    all_ids = set(base_ids)
    changed = True
    while changed:
        changed = False
        for cid in base_qs.filter(parent_id__in=all_ids).values_list('id', flat=True):
            if cid not in all_ids:
                all_ids.add(cid)
                changed = True
        for pid in (
            base_qs.filter(id__in=all_ids)
            .exclude(parent_id__isnull=True)
            .values_list('parent_id', flat=True)
        ):
            if pid not in all_ids:
                all_ids.add(pid)
                changed = True
    return all_ids


def tasks_for_workspace(user: User, team: Team | None) -> QuerySet[Task]:
    if team is not None:
        if not TeamMembership.objects.filter(team=team, user=user, is_active=True).exists():
            return Task.objects.none()
        return Task.objects.filter(team=team, is_archived=False, project__isnull=True)
    ids = personal_visible_task_ids(user)
    if not ids:
        return Task.objects.none()
    return Task.objects.filter(team__isnull=True, project__isnull=True, id__in=ids, is_archived=False)


def tasks_for_board(user: User, team: Team | None = None, project=None) -> QuerySet[Task]:
    """Tasks for mindmap/tree/kanban — project board or personal/team workspace."""
    if project is not None:
        from projects.services import user_can_access_project

        if not user_can_access_project(user, project):
            return Task.objects.none()
        return Task.objects.filter(project=project, is_archived=False)
    return tasks_for_workspace(user, team)


def task_rows_for_tree(qs: QuerySet[Task]) -> list[dict]:
    rows = []
    active_usernames_by_team: dict[int, set[str]] = {}

    def is_active_assignee(*, team_id: int | None, username: str) -> bool:
        if not team_id:
            return True
        key = int(team_id)
        if key not in active_usernames_by_team:
            active_usernames_by_team[key] = {
                (x or '').strip().lower()
                for x in TeamMembership.objects.filter(team_id=key, is_active=True)
                .values_list('user__username', flat=True)
            }
        return (username or '').strip().lower() in active_usernames_by_team[key]

    for t in qs.only(
        'id', 'parent_id', 'title', 'due_date', 'assignee_username', 'is_completed', 'team_id'
    ).order_by('id'):
        assignee = (t.assignee_username or '').strip()
        if assignee and not is_active_assignee(team_id=t.team_id, username=assignee):
            assignee = ''
        rows.append(
            {
                'id': t.id,
                'parent_id': t.parent_id,
                'title': decrypt_task_title(t.title),
                'due_date': t.due_date,
                'assignee': assignee or None,
                'is_completed': bool(t.is_completed),
            }
        )
    return rows


def root_stats(qs: QuerySet[Task]) -> tuple[int, int]:
    roots = qs.filter(parent__isnull=True)
    total = roots.count()
    done = roots.filter(is_completed=True).count()
    return total, done


def user_can_access_task(user: User, task: Task, team: Team | None = None) -> bool:
    if task.project_id:
        from projects.services import user_can_access_project

        return user_can_access_project(user, task.project)
    if team is not None:
        if task.team_id != team.id or task.project_id is not None:
            return False
        return TeamMembership.objects.filter(team=team, user=user, is_active=True).exists()
    if task.team_id is not None:
        return TeamMembership.objects.filter(team_id=task.team_id, user=user, is_active=True).exists()
    ids = personal_visible_task_ids(user)
    return task.id in ids and task.team_id is None


# ── Mind map (horizontal tree, SVG connectors) ─────────────────────────────

MINDMAP_CARD_MIN_W = 228
MINDMAP_CARD_MAX_W = 372
MINDMAP_CARD_BASE_H = 78
CMAP_CARD_MIN_W = 176
CMAP_CARD_MAX_W = 248
CMAP_CARD_BASE_H = 34
MINDMAP_COL_GAP = 36
MINDMAP_ROW_GAP = 6
MINDMAP_ROOT_GAP = 13
MINDMAP_PAD = 40

# Subtle multicolor connectors by depth for easier branch scanning.
MINDMAP_EDGE_COLORS = [
    '#94a3b8',  # slate
    '#93c5fd',  # soft blue
    '#86efac',  # soft green
    '#fcd34d',  # soft amber
    '#c4b5fd',  # soft violet
]
# Compact map: deeper connector colors (thicker strokes applied in layout).
CMAP_EDGE_COLORS = [
    '#334155',  # deep slate
    '#1d4ed8',  # deep blue
    '#15803d',  # deep green
    '#b45309',  # deep amber
    '#6d28d9',  # deep violet
]


def _connector_pull_distance(
    *,
    dx: float,
    dy: float,
    sibling_count: int,
    depth: int,
) -> float:
    """
    Dynamic curve pull for natural threads.
    - Wider columns -> longer sweep
    - Larger vertical jumps -> smoother longer bend
    - More siblings -> slight extra spacing to avoid crowding
    - Deeper levels -> slightly tighter curves
    """
    horizontal = max(min(dx * 0.48, 210.0), 28.0)
    vertical = max(min(abs(dy) * 0.18, 54.0), 0.0)
    branch_load = max(min((sibling_count - 1) * 3.0, 24.0), 0.0)
    depth_tighten = min(depth * 2.0, 10.0)
    return max(36.0, horizontal + vertical + branch_load - depth_tighten)


def _mindmap_subtree(
    node: dict,
    depth: int,
    y_ptr: list[float],
    depth_lefts: dict[int, float],
    positions: dict[int, dict],
    paths: list[dict],
    flow_style: str,
    row_gap: float,
    col_gap: float,
    *,
    dense_mode: bool = False,
) -> dict:
    """Recursive layout left → right. Fills positions and paths (parent → child Béziers)."""
    ch = node.get('children') or []
    node_w = float(node.get('_mm_w') or MINDMAP_CARD_MIN_W)
    node_h = float(node.get('_mm_h') or MINDMAP_CARD_BASE_H)
    x = depth_lefts.get(depth, float(MINDMAP_PAD))

    if not ch:
        top = y_ptr[0]
        y_ptr[0] += node_h + row_gap
        display_depth = int(node.get('_cmap_level', depth))
        positions[node['id']] = {
            'task': node,
            'left': x,
            'top': top,
            'width': node_w,
            'height': node_h,
            'depth': display_depth,
            'accent': '#6366f1',
        }
        return {'top': top, 'bottom': top + node_h}

    ranges = []
    for idx, c in enumerate(ch):
        ranges.append(
            _mindmap_subtree(
                c,
                depth + 1,
                y_ptr,
                depth_lefts,
                positions,
                paths,
                flow_style,
                row_gap,
                col_gap,
                dense_mode=dense_mode,
            )
        )
        if idx < len(ch) - 1:
            # Add breathing room between large sibling branches.
            subtree_weight = int(c.get('subtask_total') or 0)
            sibling_branch_gap = min(26.0, 4.0 + (subtree_weight * 0.65))
            y_ptr[0] += sibling_branch_gap

    min_top = min(r['top'] for r in ranges)
    max_bot = max(r['bottom'] for r in ranges)
    cy = (min_top + max_bot) / 2
    top = cy - node_h / 2
    display_depth = int(node.get('_cmap_level', depth))
    positions[node['id']] = {
        'task': node,
        'left': x,
        'top': top,
        'width': node_w,
        'height': node_h,
        'depth': display_depth,
        'accent': '#6366f1',
    }

    px_out = x + node_w
    child_count = len(ch)
    edge_colors = CMAP_EDGE_COLORS if dense_mode else MINDMAP_EDGE_COLORS
    for idx, c in enumerate(ch):
        cp = positions[c['id']]
        cy_c = cp['top'] + cp['height'] / 2
        cx_in = cp['left']
        stroke = edge_colors[(depth + idx + 1) % len(edge_colors)]
        dx = cx_in - px_out
        py = cy
        dy = cy_c - py
        pull = _connector_pull_distance(
            dx=dx,
            dy=dy,
            sibling_count=child_count,
            depth=depth,
        )
        c1x = px_out + pull
        c2x = cx_in - pull
        d = f'M {px_out:.1f},{py:.1f} C {c1x:.1f},{py:.1f} {c2x:.1f},{cy_c:.1f} {cx_in:.1f},{cy_c:.1f}'
        # Smoother visual hierarchy for connectors:
        # stronger near root, lighter on deeper levels.
        stroke_w = max(1.15, 1.95 - (depth * 0.18))
        stroke_opacity = max(0.46, 0.86 - (depth * 0.08))
        if dense_mode:
            stroke_w = max(2.3, stroke_w * 2.0)
            stroke_opacity = min(0.95, max(0.72, stroke_opacity + 0.12))
        dash = ''
        paths.append(
            {
                'd': d,
                'stroke': stroke,
                'stroke_w': stroke_w,
                'opacity': stroke_opacity,
                'dash': dash,
            }
        )

    return {'top': top, 'bottom': top + node_h}


def _mindmap_node_size(
    node: dict, *, compact_mode: bool = False, dense_mode: bool = False
) -> tuple[int, int]:
    if compact_mode:
        title = str(node.get('title') or '').strip()
        if not title:
            return (160, 28)
        title_len = len(title)
        # Idea mode should show full title without trimming in collapsed state.
        width = min(520, max(160, 140 + (title_len * 6)))
        return (int(width), 28)

    if dense_mode:
        title = str(node.get('title') or '').strip()
        if not title:
            return (CMAP_CARD_MIN_W, CMAP_CARD_BASE_H)
        title_len = len(title)
        # Fixed two-row chip height so actions stay visible and layout is stable.
        width = min(CMAP_CARD_MAX_W, max(CMAP_CARD_MIN_W, 140 + (title_len * 3)))
        return (int(width), CMAP_CARD_BASE_H)

    title = str(node.get('title') or '').strip()
    if not title:
        return (MINDMAP_CARD_MIN_W, MINDMAP_CARD_BASE_H)
    words = title.split()
    title_len = len(title)
    longest_word = max((len(w) for w in words), default=0)
    width_boost = max(title_len - 28, 0) * 2 + max(longest_word - 14, 0) * 3
    width = min(MINDMAP_CARD_MAX_W, MINDMAP_CARD_MIN_W + width_boost)
    chars_per_line = max(24, int(width // 8))
    est_lines = max(1, min(4, (title_len + chars_per_line - 1) // chars_per_line))
    height = MINDMAP_CARD_BASE_H + ((est_lines - 1) * 14)
    return (int(width), int(height))


def _annotate_mindmap_sizes(
    roots: list[dict],
    *,
    col_gap: float,
    compact_mode: bool = False,
    dense_mode: bool = False,
) -> tuple[dict[int, float], int, int]:
    depth_widths: dict[int, float] = {}
    max_w = CMAP_CARD_MIN_W if dense_mode else MINDMAP_CARD_MIN_W
    max_h = CMAP_CARD_BASE_H if dense_mode else MINDMAP_CARD_BASE_H

    def walk(node: dict, depth: int) -> None:
        nonlocal max_w, max_h
        width, height = _mindmap_node_size(
            node, compact_mode=compact_mode, dense_mode=dense_mode
        )
        node['_mm_w'] = width
        node['_mm_h'] = height
        depth_widths[depth] = max(depth_widths.get(depth, 0.0), float(width))
        max_w = max(max_w, width)
        max_h = max(max_h, height)
        for child in node.get('children') or []:
            walk(child, depth + 1)

    for root in roots:
        walk(root, 0)

    depth_lefts: dict[int, float] = {}
    cursor = float(MINDMAP_PAD)
    for depth in sorted(depth_widths.keys()):
        depth_lefts[depth] = cursor
        cursor += depth_widths[depth] + col_gap
    return depth_lefts, max_w, max_h


def mindmap_collapse_session_key(team: Team | None, project=None) -> str:
    if project is not None:
        return f'mm_collapse_proj_{project.slug}'
    return f"mm_collapse_t_{team.slug}" if team else 'mm_collapse_p'


def get_mindmap_collapsed_ids(
    request,
    team: Team | None,
    *,
    project=None,
    tree: list[dict] | None = None,
) -> set[int]:
    all_branch_ids = set(collect_branch_ids_with_children(tree or [])) if tree is not None else set()

    key = mindmap_collapse_session_key(team, project)
    if key not in request.session:
        request.session[key] = []
        request.session.modified = True
    raw = request.session.get(key, [])
    if not isinstance(raw, list):
        return set()
    out: set[int] = set()
    for x in raw:
        try:
            out.add(int(x))
        except (TypeError, ValueError):
            continue
    if all_branch_ids and out == all_branch_ids:
        request.session[key] = []
        request.session.modified = True
        return set()
    return out


def set_mindmap_collapsed_ids(
    request, team: Team | None, ids: set[int], *, project=None
) -> None:
    key = mindmap_collapse_session_key(team, project)
    request.session[key] = sorted(ids)
    request.session.modified = True


def collect_task_has_children(roots: list[dict]) -> dict[int, int]:
    """Returns {task_id: direct_child_count}. Count is from the full (unpruned) tree."""
    out: dict[int, int] = {}

    def walk(n: dict) -> None:
        ch = n.get('children') or []
        out[n['id']] = len(ch)
        for c in ch:
            walk(c)

    for r in roots:
        walk(r)
    return out


def collect_branch_ids_with_children(roots: list[dict]) -> list[int]:
    """Task ids that have at least one child (mind map branches collapsed by default)."""
    out: list[int] = []

    def walk(n: dict) -> None:
        ch = n.get('children') or []
        if ch:
            out.append(int(n['id']))
            for c in ch:
                walk(c)

    for r in roots:
        walk(r)
    return out


def prune_mindmap_tree(roots: list[dict], collapsed_ids: set[int]) -> list[dict]:
    """Drop children for any node id in collapsed_ids (mind map branch collapse)."""

    def clone(n: dict) -> dict:
        c = {k: v for k, v in n.items() if k != 'children'}
        ch = n.get('children') or []
        if n['id'] in collapsed_ids:
            c['children'] = []
        else:
            c['children'] = [clone(x) for x in ch]
        return c

    return [clone(r) for r in roots]


def cmap_focus_session_key(team: Team | None, project=None) -> str:
    if project is not None:
        return f'cmap_focus_proj_{project.slug}'
    return f'cmap_focus_t_{team.slug}' if team else 'cmap_focus_p'


def get_cmap_focus_depth(request, team: Team | None, *, project=None) -> int | None:
    """Compact map level focus: 1=33D, 2=11D, 3=1D, None=full tree."""
    key = cmap_focus_session_key(team, project)
    raw = request.session.get(key)
    if raw in (1, 2, 3):
        return int(raw)
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return None
    return val if val in (1, 2, 3) else None


def set_cmap_focus_depth(
    request, team: Team | None, depth: int | None, *, project=None
) -> None:
    key = cmap_focus_session_key(team, project)
    if depth in (1, 2, 3):
        request.session[key] = int(depth)
    else:
        request.session.pop(key, None)
    request.session.modified = True


def extract_nodes_at_depth(roots: list[dict], depth: int) -> list[dict]:
    """
    Compact level-focus: return only nodes at `depth` as roots (no children).
    Preserves `_cmap_level` so badges/colors stay correct after re-rooting.
    """
    found: list[dict] = []

    def walk(n: dict, d: int) -> None:
        if d == depth:
            c = {k: v for k, v in n.items() if k != 'children'}
            c['children'] = []
            c['_cmap_level'] = depth
            found.append(c)
            return
        for ch in n.get('children') or []:
            walk(ch, d + 1)

    for r in roots:
        walk(r, 0)
    return found


def prepare_mindmap_roots(
    roots: list[dict],
    collapsed_ids: set[int],
    *,
    layout: str,
    cmap_focus_depth: int | None = None,
) -> list[dict]:
    """Prune by collapse, or (cmap only) show a single depth for focus."""
    if layout == 'cmap' and cmap_focus_depth in (1, 2, 3):
        return extract_nodes_at_depth(roots, int(cmap_focus_depth))
    return prune_mindmap_tree(roots, collapsed_ids)


def compute_mindmap_layout(
    roots: list[dict],
    *,
    flow_style: str = 'natural',
    compact_mode: bool = False,
    dense_mode: bool = False,
) -> dict:
    """
    Build node positions and cubic SVG paths for a forest of task trees.
    """
    empty = {
        'nodes': [],
        'paths': [],
        'width': 920,
        'height': 480,
        'card_w': CMAP_CARD_MIN_W if dense_mode else MINDMAP_CARD_MIN_W,
        'card_h': CMAP_CARD_BASE_H if dense_mode else MINDMAP_CARD_BASE_H,
    }
    if not roots:
        return empty

    total_nodes = sum(1 + int(r.get('subtask_total') or 0) for r in roots)
    density_boost = min(46.0, max(0.0, total_nodes - 6) * 1.8)

    if dense_mode:
        # Compact map chips: readable packing without stacking/overlap.
        row_gap = 10.0 + (density_boost * 0.22)
        col_gap = 36.0 + (density_boost * 0.24)
        root_gap = 18.0 + (density_boost * 0.22)
    elif compact_mode:
        # Idea mode keeps cards collapsed visually, but hover reveals extra controls.
        row_gap = 34.0 + (density_boost * 0.36)
        col_gap = 56.0 + (density_boost * 0.40)
        root_gap = 44.0 + (density_boost * 0.34)
    elif flow_style == 'tight':
        row_gap = 2.0 + (density_boost * 0.22)
        col_gap = 20.0 + (density_boost * 0.26)
        root_gap = 8.0 + (density_boost * 0.26)
    elif flow_style == 'relaxed':
        row_gap = 30.0 + (density_boost * 1.3)
        col_gap = 110.0 + (density_boost * 1.25)
        root_gap = 46.0 + (density_boost * 1.15)
    else:
        row_gap = 12.0 + (density_boost * 0.68)
        col_gap = 60.0 + (density_boost * 0.72)
        root_gap = 22.0 + (density_boost * 0.62)

    positions: dict[int, dict] = {}
    paths: list[dict] = []
    y_ptr = [float(MINDMAP_PAD)]
    depth_lefts, max_card_w, max_card_h = _annotate_mindmap_sizes(
        roots,
        col_gap=col_gap,
        compact_mode=compact_mode,
        dense_mode=dense_mode,
    )
    for root in roots:
        _mindmap_subtree(
            root,
            0,
            y_ptr,
            depth_lefts,
            positions,
            paths,
            flow_style,
            row_gap,
            col_gap,
            dense_mode=dense_mode,
        )
        y_ptr[0] += root_gap

    nodes = sorted(positions.values(), key=lambda n: (n['top'], n['left'], n['task']['id']))
    width = int(max(n['left'] + n['width'] for n in nodes) + MINDMAP_PAD)
    height = int(max(n['top'] + n['height'] for n in nodes) + MINDMAP_PAD)
    return {
        'nodes': nodes,
        'paths': paths,
        'width': max(width, 640),
        'height': max(height, 360),
        'card_w': max_card_w,
        'card_h': max_card_h,
    }


def notify_assignee(*, assignee_username: str, actor: User, title: str, old_assignee: str) -> None:
    if not assignee_username or assignee_username == actor.username:
        return
    if assignee_username == (old_assignee or ''):
        return
    try:
        u = User.objects.get(username__iexact=assignee_username)
    except User.DoesNotExist:
        return
    msg = f'{actor.username} assigned you to task "{title}"'
    Notification.objects.create(user=u, message=msg)


def assignee_choices(*, actor: User, team: Team | None, project=None) -> list[str]:
    """
    Assign list for UI selects:
    - Project board → project members only (always includes you)
    - Team board → active team members (always includes you)
    - Personal board → just you
    """
    if project is not None:
        from projects.models import ProjectMember

        usernames = (
            ProjectMember.objects.filter(project=project)
            .select_related('user')
            .values_list('user__username', flat=True)
        )
        clean = {(u or '').strip() for u in usernames if (u or '').strip()}
        if project.owner_id:
            owner_name = (getattr(project.owner, 'username', '') or '').strip()
            if not owner_name:
                owner = User.objects.filter(pk=project.owner_id).only('username').first()
                owner_name = (owner.username if owner else '') or ''
            if owner_name:
                clean.add(owner_name)
        me = (actor.username or '').strip()
        if me:
            clean.add(me)
        return sorted(clean, key=str.lower)

    if team is not None:
        usernames = (
            TeamMembership.objects.filter(team=team, is_active=True)
            .select_related('user')
            .values_list('user__username', flat=True)
        )
        clean = {(u or '').strip() for u in usernames if (u or '').strip()}
        me = (actor.username or '').strip()
        if me:
            clean.add(me)
        return sorted(clean, key=str.lower)
    me = (actor.username or '').strip()
    return [me] if me else []


def resolve_assignee(
    *,
    actor: User,
    team: Team | None,
    raw: str,
    project=None,
) -> tuple[str, str | None]:
    """
    Normalize assignee input.
    Returns (canonical_username_or_empty, error_message_or_None).
    Empty string = unassigned.
    """
    assignee = (raw or '').strip()
    if not assignee:
        return '', None

    user = User.objects.filter(username__iexact=assignee).only('id', 'username').first()
    if user is None:
        return '', 'Person not found. Pick someone from the list.'

    if project is not None:
        from projects.services import user_can_access_project

        if not user_can_access_project(user, project):
            return '', 'Pick a project member (or Unassigned).'
        return user.username, None

    if team is None:
        if user.id != actor.id:
            return '', 'On personal boards, assign only to yourself (or leave unassigned).'
        return user.username, None

    is_member = TeamMembership.objects.filter(
        team=team, user=user, is_active=True
    ).exists()
    if not is_member:
        return '', 'Pick an active team member (or Unassigned).'
    return user.username, None


def task_depth(task: Task) -> int:
    """0 = 99D, 1 = 33D, 2 = 11D, 3 = 1D, 4+ = ST subtasks."""
    depth = 0
    current = task
    seen: set[int] = set()
    while current is not None and current.parent_id is not None:
        if current.id in seen:
            break
        seen.add(current.id)
        depth += 1
        current = current.parent
    return depth


def sync_parent_completion_from_children(task: Task | None) -> None:
    """
    Keep branch completion status consistent:
    - parent is completed iff all its direct children are completed
    - applies recursively upward to root
    """
    if task is None:
        return
    # `task` is treated as the first parent node to recalculate.
    current = task
    while current is not None:
        has_children = Task.objects.filter(parent_id=current.id).exists()
        if has_children:
            all_children_done = not Task.objects.filter(
                parent_id=current.id,
                is_completed=False,
            ).exists()
            if current.is_completed != all_children_done:
                current.is_completed = all_children_done
                if all_children_done:
                    current.status = Task.STATUS_DONE
                    current.save(update_fields=['is_completed', 'status'])
                else:
                    if current.status == Task.STATUS_DONE:
                        current.status = Task.STATUS_TODO
                        current.save(update_fields=['is_completed', 'status'])
                    else:
                        current.save(update_fields=['is_completed'])
        current = current.parent


def sync_descendant_completion(task: Task, is_completed: bool) -> None:
    """
    Apply completion status to all descendants of a task.
    Used for branch-level consistency when toggling parent/branch tasks.
    """
    child_ids = list(Task.objects.filter(parent_id=task.id).values_list('id', flat=True))
    while child_ids:
        Task.objects.filter(id__in=child_ids).update(is_completed=is_completed)
        child_ids = list(Task.objects.filter(parent_id__in=child_ids).values_list('id', flat=True))


def workspace_root_average_percent(qs: QuerySet[Task]) -> int:
    """
    Sidebar completion metric:
    average of root task percentages (0-100), rounded to int.
    Only needs id/parent_id/is_completed, so skip title decryption entirely.
    """
    rows = list(qs.values('id', 'parent_id', 'is_completed'))
    roots = build_task_tree(rows)
    if not roots:
        return 0
    total = sum(int(r.get('percent') or 0) for r in roots)
    return int(round(total / len(roots)))


def workspace_root_average_percent_by_team(user: User, team_ids: list[int]) -> dict[int, int]:
    """
    Batched sidebar completion metric for multiple teams in one query,
    instead of one tasks_for_workspace() query per team.
    """
    if not team_ids:
        return {}
    rows_by_team: dict[int, list[dict]] = {tid: [] for tid in team_ids}
    for row in Task.objects.filter(
        team_id__in=team_ids, is_archived=False, project__isnull=True
    ).values('id', 'parent_id', 'team_id', 'is_completed'):
        rows_by_team[row['team_id']].append(row)

    result: dict[int, int] = {}
    for tid, rows in rows_by_team.items():
        roots = build_task_tree(rows)
        if not roots:
            result[tid] = 0
            continue
        total = sum(int(r.get('percent') or 0) for r in roots)
        result[tid] = int(round(total / len(roots)))
    return result


def normalize_workspace_completion(qs: QuerySet[Task]) -> bool:
    """
    Self-heal completion consistency for a workspace.
    For any task with children, `is_completed` must equal all(children completed).
    This fixes historical/stale inconsistencies before tree/mindmap calculations.
    """
    rows = list(qs.values('id', 'parent_id', 'is_completed'))
    if not rows:
        return

    parent_by_id: dict[int, int | None] = {}
    children_by_parent: dict[int, list[int]] = {}
    state: dict[int, bool] = {}
    for r in rows:
        tid = int(r['id'])
        pid = r['parent_id']
        pid_i = int(pid) if pid is not None else None
        parent_by_id[tid] = pid_i
        state[tid] = bool(r['is_completed'])
        if pid_i is not None:
            children_by_parent.setdefault(pid_i, []).append(tid)

    depth_cache: dict[int, int] = {}

    def depth(tid: int) -> int:
        if tid in depth_cache:
            return depth_cache[tid]
        pid = parent_by_id.get(tid)
        if pid is None:
            depth_cache[tid] = 0
            return 0
        d = depth(pid) + 1
        depth_cache[tid] = d
        return d

    for tid in parent_by_id.keys():
        depth(tid)

    changed_ids: list[int] = []
    for tid in sorted(parent_by_id.keys(), key=lambda x: depth_cache[x], reverse=True):
        children = children_by_parent.get(tid, [])
        if not children:
            continue
        desired = all(state[cid] for cid in children)
        if state[tid] != desired:
            state[tid] = desired
            changed_ids.append(tid)

    if not changed_ids:
        return False
    Task.objects.filter(id__in=changed_ids).update(is_completed=False)
    Task.objects.filter(id__in=[x for x in changed_ids if state[x]]).update(is_completed=True)
    return True
