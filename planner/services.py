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

MINDMAP_CARD_W = 268
MINDMAP_CARD_H = 82
MINDMAP_COL_GAP = 36
MINDMAP_ROW_GAP = 6
MINDMAP_ROOT_GAP = 13
MINDMAP_PAD = 40

# Branch curves — distinct hues aligned with card depth accents
MINDMAP_EDGE_COLORS = [
    '#ea580c',  # orange — depth 0
    '#0891b2',  # cyan — depth 1
    '#db2777',  # pink — depth 2
    '#65a30d',  # lime — depth 3+
    '#7c3aed',  # violet (extra cycle)
    '#ca8a04',  # yellow-600
    '#4f46e5',  # indigo
]


def _mindmap_subtree(
    node: dict,
    depth: int,
    y_ptr: list[float],
    positions: dict[int, dict],
    paths: list[dict],
) -> dict:
    """Recursive layout left → right. Fills positions and paths (parent → child Béziers)."""
    ch = node.get('children') or []
    x = depth * (MINDMAP_CARD_W + MINDMAP_COL_GAP) + MINDMAP_PAD
    color = MINDMAP_EDGE_COLORS[depth % len(MINDMAP_EDGE_COLORS)]

    if not ch:
        top = y_ptr[0]
        y_ptr[0] += MINDMAP_CARD_H + MINDMAP_ROW_GAP
        positions[node['id']] = {
            'task': node,
            'left': x,
            'top': top,
            'depth': depth,
            'accent': color,
        }
        return {'top': top, 'bottom': top + MINDMAP_CARD_H}

    ranges = []
    for c in ch:
        ranges.append(_mindmap_subtree(c, depth + 1, y_ptr, positions, paths))

    min_top = min(r['top'] for r in ranges)
    max_bot = max(r['bottom'] for r in ranges)
    cy = (min_top + max_bot) / 2
    top = cy - MINDMAP_CARD_H / 2
    positions[node['id']] = {
        'task': node,
        'left': x,
        'top': top,
        'depth': depth,
        'accent': color,
    }

    px_out = x + MINDMAP_CARD_W
    for c in ch:
        cp = positions[c['id']]
        cy_c = cp['top'] + MINDMAP_CARD_H / 2
        cx_in = cp['left']
        stroke = MINDMAP_EDGE_COLORS[(depth + 1) % len(MINDMAP_EDGE_COLORS)]
        dx = cx_in - px_out
        pull = max(min(dx * 0.55, 140), 48)
        c1x = px_out + pull
        c2x = cx_in - pull
        d = f'M {px_out:.1f},{cy:.1f} C {c1x:.1f},{cy:.1f} {c2x:.1f},{cy_c:.1f} {cx_in:.1f},{cy_c:.1f}'
        paths.append({'d': d, 'stroke': stroke})

    return {'top': top, 'bottom': top + MINDMAP_CARD_H}


def mindmap_collapse_session_key(team: Team | None) -> str:
    return f"mm_collapse_t_{team.slug}" if team else 'mm_collapse_p'


def get_mindmap_collapsed_ids(
    request,
    team: Team | None,
    *,
    tree: list[dict] | None = None,
) -> set[int]:
    if team is not None:
        raw = team.mindmap_collapsed_task_ids
        if raw is None:
            if tree is None:
                return set()
            collapsed = set(collect_branch_ids_with_children(tree))
            team.mindmap_collapsed_task_ids = sorted(collapsed)
            team.save(update_fields=['mindmap_collapsed_task_ids'])
            return collapsed
        if not isinstance(raw, list):
            return set()
        out: set[int] = set()
        for x in raw:
            try:
                out.add(int(x))
            except (TypeError, ValueError):
                continue
        return out

    key = mindmap_collapse_session_key(team)
    if key not in request.session:
        if tree is not None:
            request.session[key] = sorted(collect_branch_ids_with_children(tree))
            request.session.modified = True
        else:
            return set()
    raw = request.session.get(key, [])
    if not isinstance(raw, list):
        return set()
    out: set[int] = set()
    for x in raw:
        try:
            out.add(int(x))
        except (TypeError, ValueError):
            continue
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


def compute_mindmap_layout(roots: list[dict]) -> dict:
    """
    Build node positions and cubic SVG paths for a forest of task trees.
    """
    empty = {
        'nodes': [],
        'paths': [],
        'width': 920,
        'height': 480,
        'card_w': MINDMAP_CARD_W,
        'card_h': MINDMAP_CARD_H,
    }
    if not roots:
        return empty

    positions: dict[int, dict] = {}
    paths: list[dict] = []
    y_ptr = [float(MINDMAP_PAD)]
    for root in roots:
        _mindmap_subtree(root, 0, y_ptr, positions, paths)
        y_ptr[0] += MINDMAP_ROOT_GAP

    nodes = sorted(positions.values(), key=lambda n: (n['top'], n['left'], n['task']['id']))
    width = int(max(n['left'] + MINDMAP_CARD_W for n in nodes) + MINDMAP_PAD)
    height = int(max(n['top'] + MINDMAP_CARD_H for n in nodes) + MINDMAP_PAD)
    return {
        'nodes': nodes,
        'paths': paths,
        'width': max(width, 640),
        'height': max(height, 360),
        'card_w': MINDMAP_CARD_W,
        'card_h': MINDMAP_CARD_H,
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
