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
) -> Task:
    return Task.objects.create(
        author=author,
        team=team,
        parent=parent,
        title=title.strip(),
        due_date=due_date,
        assignee_username=(assignee_username or '').strip(),
    )


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
    tree = []
    siblings = [t for t in tasks if t['parent_id'] == parent_id]
    siblings.sort(key=lambda t: t['id'], reverse=(parent_id is None))

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
        node['children'] = build_task_tree(tasks, task['id'])
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
        return Task.objects.filter(team=team, is_archived=False)
    ids = personal_visible_task_ids(user)
    if not ids:
        return Task.objects.none()
    return Task.objects.filter(team__isnull=True, id__in=ids, is_archived=False)


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

    for t in qs.order_by('id'):
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


def user_can_access_task(user: User, task: Task, team: Team | None) -> bool:
    if team is not None:
        if task.team_id != team.id:
            return False
        return TeamMembership.objects.filter(team=team, user=user, is_active=True).exists()
    ids = personal_visible_task_ids(user)
    return task.id in ids and task.team_id is None


# ── Mind map (horizontal tree, SVG connectors) ─────────────────────────────

MINDMAP_CARD_MIN_W = 228
MINDMAP_CARD_MAX_W = 372
MINDMAP_CARD_BASE_H = 78
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
) -> dict:
    """Recursive layout left → right. Fills positions and paths (parent → child Béziers)."""
    ch = node.get('children') or []
    node_w = float(node.get('_mm_w') or MINDMAP_CARD_MIN_W)
    node_h = float(node.get('_mm_h') or MINDMAP_CARD_BASE_H)
    x = depth_lefts.get(depth, float(MINDMAP_PAD))

    if not ch:
        top = y_ptr[0]
        y_ptr[0] += node_h + row_gap
        positions[node['id']] = {
            'task': node,
            'left': x,
            'top': top,
            'width': node_w,
            'height': node_h,
            'depth': depth,
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
    positions[node['id']] = {
        'task': node,
        'left': x,
        'top': top,
        'width': node_w,
        'height': node_h,
        'depth': depth,
        'accent': '#6366f1',
    }

    px_out = x + node_w
    child_count = len(ch)
    for idx, c in enumerate(ch):
        cp = positions[c['id']]
        cy_c = cp['top'] + cp['height'] / 2
        cx_in = cp['left']
        stroke = MINDMAP_EDGE_COLORS[(depth + idx + 1) % len(MINDMAP_EDGE_COLORS)]
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
        stroke_w = 1.5
        stroke_opacity = 0.8
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


def _mindmap_node_size(node: dict) -> tuple[int, int]:
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
) -> tuple[dict[int, float], int, int]:
    depth_widths: dict[int, float] = {}
    max_w = MINDMAP_CARD_MIN_W
    max_h = MINDMAP_CARD_BASE_H

    def walk(node: dict, depth: int) -> None:
        nonlocal max_w, max_h
        width, height = _mindmap_node_size(node)
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


def mindmap_collapse_session_key(team: Team | None) -> str:
    return f"mm_collapse_t_{team.slug}" if team else 'mm_collapse_p'


def get_mindmap_collapsed_ids(
    request,
    team: Team | None,
    *,
    tree: list[dict] | None = None,
) -> set[int]:
    all_branch_ids = set(collect_branch_ids_with_children(tree or [])) if tree is not None else set()

    if team is not None:
        raw = team.mindmap_collapsed_task_ids
        if raw is None:
            # Default to expanded branches; user can collapse manually.
            return set()
        if not isinstance(raw, list):
            return set()
        out: set[int] = set()
        for x in raw:
            try:
                out.add(int(x))
            except (TypeError, ValueError):
                continue
        # Backward compatibility: old behavior stored "all branches collapsed" by default.
        # Auto-heal such state to expanded unless user explicitly collapses again.
        if all_branch_ids and out == all_branch_ids:
            team.mindmap_collapsed_task_ids = []
            team.save(update_fields=['mindmap_collapsed_task_ids'])
            return set()
        return out

    key = mindmap_collapse_session_key(team)
    if key not in request.session:
        # Default to expanded branches; user can collapse manually.
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


def set_mindmap_collapsed_ids(request, team: Team | None, ids: set[int]) -> None:
    if team is not None:
        team.mindmap_collapsed_task_ids = sorted(ids)
        team.save(update_fields=['mindmap_collapsed_task_ids'])
        return
    key = mindmap_collapse_session_key(team)
    request.session[key] = sorted(ids)
    request.session.modified = True


def collect_task_has_children(roots: list[dict]) -> dict[int, bool]:
    out: dict[int, bool] = {}

    def walk(n: dict) -> None:
        ch = n.get('children') or []
        out[n['id']] = len(ch) > 0
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


def compute_mindmap_layout(roots: list[dict], *, flow_style: str = 'natural') -> dict:
    """
    Build node positions and cubic SVG paths for a forest of task trees.
    """
    empty = {
        'nodes': [],
        'paths': [],
        'width': 920,
        'height': 480,
        'card_w': MINDMAP_CARD_MIN_W,
        'card_h': MINDMAP_CARD_BASE_H,
    }
    if not roots:
        return empty

    total_nodes = sum(1 + int(r.get('subtask_total') or 0) for r in roots)
    density_boost = min(46.0, max(0.0, total_nodes - 6) * 1.8)

    if flow_style == 'tight':
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
    depth_lefts, max_card_w, max_card_h = _annotate_mindmap_sizes(roots, col_gap=col_gap)
    for root in roots:
        _mindmap_subtree(root, 0, y_ptr, depth_lefts, positions, paths, flow_style, row_gap, col_gap)
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
    """
    rows = task_rows_for_tree(qs)
    roots = build_task_tree(rows)
    if not roots:
        return 0
    total = sum(int(r.get('percent') or 0) for r in roots)
    return int(round(total / len(roots)))


def normalize_workspace_completion(qs: QuerySet[Task]) -> None:
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
        return
    Task.objects.filter(id__in=changed_ids).update(is_completed=False)
    Task.objects.filter(id__in=[x for x in changed_ids if state[x]]).update(is_completed=True)
