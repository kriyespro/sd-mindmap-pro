import json
import csv
from html import escape as html_escape

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import TemplateView
from django.views.decorators.csrf import ensure_csrf_cookie

from planner.context_processors import workspace_chrome
from planner.forms import TaskCreateForm, TaskImportForm, TaskMetaForm, TaskTitleForm
from planner.crypto import decrypt_task_title
from planner.models import Notification, Task
from planner.services import (
    assignee_choices,
    build_task_tree,
    collect_branch_ids_with_children,
    collect_task_has_children,
    compute_mindmap_layout,
    create_99d_template,
    get_mindmap_collapsed_ids,
    import_tasks_from_upload,
    normalize_workspace_completion,
    notify_assignee,
    prune_mindmap_tree,
    resolve_assignee,
    root_stats,
    sync_descendant_completion,
    sync_parent_completion_from_children,
    workspace_root_average_percent,
    set_mindmap_collapsed_ids,
    task_rows_for_tree,
    tasks_for_board,
    tasks_for_workspace,
    user_can_access_task,
)
from teams.forms import TeamCreateForm, TeamInviteForm
from teams.models import Team, TeamMembership
from users.models import Profile
from users.services import is_tutorial_project
from users.ui_mode import get_user_ui_mode, normalize_layout

User = get_user_model()


class WorkspaceUrls:
    __slots__ = ('_team_slug', '_project_slug')

    def __init__(self, team: Team | None = None, project=None):
        self._team_slug = team.slug if team else None
        self._project_slug = project.slug if project else None

    @property
    def is_project(self) -> bool:
        return self._project_slug is not None

    def _reverse(self, project_name: str, team_name: str, personal_name: str, **kwargs) -> str:
        if self._project_slug:
            return reverse(
                f'projects:{project_name}',
                kwargs={'slug': self._project_slug, **kwargs},
            )
        if self._team_slug:
            return reverse(f'planner:{team_name}', kwargs={'team_slug': self._team_slug, **kwargs})
        return reverse(f'planner:{personal_name}', kwargs=kwargs)

    @property
    def stats(self) -> str:
        return self._reverse('board_stats', 'stats_team', 'stats_personal')

    @property
    def tasks(self) -> str:
        return self._reverse('board_task_create', 'task_create_team', 'task_create_personal')

    @property
    def tree_partial(self) -> str:
        return self._reverse(
            'board_task_tree_partial', 'task_tree_partial_team', 'task_tree_partial_personal'
        )

    @property
    def task_import(self) -> str:
        if self._project_slug:
            return ''
        if self._team_slug:
            return reverse('planner:task_import_team', kwargs={'team_slug': self._team_slug})
        return reverse('planner:task_import_personal')

    @property
    def task_export(self) -> str:
        if self._project_slug:
            return ''
        if self._team_slug:
            return reverse('planner:task_export_team', kwargs={'team_slug': self._team_slug})
        return reverse('planner:task_export_personal')

    def toggle(self, task_id: int) -> str:
        return self._reverse(
            'board_task_toggle', 'task_toggle_team', 'task_toggle_personal', task_id=task_id
        )

    def delete(self, task_id: int) -> str:
        return self._reverse(
            'board_task_delete', 'task_delete_team', 'task_delete_personal', task_id=task_id
        )

    def title(self, task_id: int) -> str:
        return self._reverse(
            'board_task_title', 'task_title_team', 'task_title_personal', task_id=task_id
        )

    def meta(self, task_id: int) -> str:
        return self._reverse(
            'board_task_meta', 'task_meta_team', 'task_meta_personal', task_id=task_id
        )

    def mindmap_collapse(self, task_id: int) -> str:
        return self._reverse(
            'board_mindmap_collapse',
            'mindmap_collapse_team',
            'mindmap_collapse_personal',
            task_id=task_id,
        )

    @property
    def mindmap_collapse_all(self) -> str:
        return self._reverse(
            'board_mindmap_collapse_all',
            'mindmap_collapse_all_team',
            'mindmap_collapse_all_personal',
        )

    @property
    def mindmap_expand_all(self) -> str:
        return self._reverse(
            'board_mindmap_expand_all',
            'mindmap_expand_all_team',
            'mindmap_expand_all_personal',
        )

    def kanban_status(self, task_id: int) -> str:
        return self._reverse(
            'board_kanban_status', 'kanban_status_team', 'kanban_status_personal', task_id=task_id
        )


def workspace_urls(team: Team | None = None, project=None) -> WorkspaceUrls:
    return WorkspaceUrls(team, project)


def _set_tree_focus_expand_ids(request, ids: set[int]) -> None:
    request.session['tree_focus_expand_ids'] = sorted(ids)
    request.session.modified = True


def _get_tree_focus_expand_ids(request) -> list[int]:
    raw = request.session.get('tree_focus_expand_ids', [])
    if not isinstance(raw, list):
        return []
    out: list[int] = []
    for x in raw:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out


def _workspace_team(user, team_slug: str | None) -> Team | None:
    if not team_slug:
        return None
    team = get_object_or_404(Team, slug=team_slug)
    if not TeamMembership.objects.filter(team=team, user=user, is_active=True).exists():
        return None
    return team


def _workspace_project(user, project_slug: str | None):
    if not project_slug:
        return None
    from projects.models import Project
    from projects.services import user_can_access_project

    project = get_object_or_404(Project, slug=project_slug, is_archived=False)
    if not user_can_access_project(user, project):
        return None
    return project


def _resolve_board(user, team_slug: str | None = None, project_slug: str | None = None):
    if project_slug:
        project = _workspace_project(user, project_slug)
        if project is None:
            raise Http404('Project not found')
        return None, project
    team = _workspace_team(user, team_slug)
    if team_slug and team is None:
        raise Http404('Team not found')
    return team, None


def _board_queryset(user, team, project):
    qs = tasks_for_board(user, team=team, project=project)
    if normalize_workspace_completion(qs):
        qs = tasks_for_board(user, team=team, project=project)
    return qs


def _board_task_tree(user, team, project):
    qs = _board_queryset(user, team, project)
    rows = task_rows_for_tree(qs)
    return qs, build_task_tree(rows)


def _sync_task_completion_fields(task: Task) -> None:
    if task.is_completed:
        task.status = Task.STATUS_DONE
    elif task.status == Task.STATUS_DONE:
        task.status = Task.STATUS_TODO


def _maybe_update_project_progress(task: Task) -> None:
    if task.project_id:
        from projects.services import update_project_progress

        update_project_progress(task.project)


def _active_team_usernames(team: Team | None) -> list[str]:
    if team is None:
        return []
    usernames = (
        TeamMembership.objects.filter(team=team, is_active=True)
        .select_related('user')
        .values_list('user__username', flat=True)
    )
    clean = [(u or '').strip() for u in usernames]
    return sorted({u for u in clean if u}, key=str.lower)


def _validate_assignee_for_workspace(
    *,
    actor: User,
    team: Team | None,
    assignee_username: str,
    project=None,
) -> tuple[str, str | None]:
    """Returns (canonical_username, error_or_None). Empty username = unassigned."""
    return resolve_assignee(
        actor=actor, team=team, raw=assignee_username, project=project
    )


def _task_ancestor_ids(task: Task) -> set[int]:
    ancestor_ids: set[int] = set()
    current = task
    while current.parent_id is not None:
        ancestor_ids.add(int(current.parent_id))
        current = current.parent
    return ancestor_ids


def _direct_branch_child_ids(roots: list[dict], parent_id: int) -> set[int]:
    """Return direct child ids that themselves have children (branch nodes)."""

    def walk(nodes: list[dict]) -> set[int]:
        for node in nodes:
            if int(node.get('id', 0)) == parent_id:
                branch_ids: set[int] = set()
                for child in node.get('children') or []:
                    if child.get('children'):
                        branch_ids.add(int(child['id']))
                return branch_ids
            out = walk(node.get('children') or [])
            if out:
                return out
        return set()

    return walk(roots)


def _svg_text_lines(value: str, max_chars: int = 24, max_lines: int = 3) -> list[str]:
    text = (value or '').strip()
    if not text:
        return ['(untitled)']
    words = text.split()
    lines: list[str] = []
    cur = ''
    for w in words:
        next_value = f'{cur} {w}'.strip()
        if len(next_value) <= max_chars:
            cur = next_value
            continue
        if cur:
            lines.append(cur)
        cur = w
        if len(lines) >= max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if len(lines) == max_lines and len(' '.join(words)) > sum(len(x) for x in lines):
        lines[-1] = (lines[-1][: max(0, max_chars - 1)] + '…') if lines[-1] else '…'
    return lines


def _mindmap_svg_bytes(*, tree: list[dict], flow_style: str = 'natural') -> bytes:
    layout = compute_mindmap_layout(tree, flow_style=flow_style)
    width = max(int(layout['width']), 640)
    height = max(int(layout['height']), 360)
    out: list[str] = []
    out.append(
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">'
        )
    )
    out.append('<rect x="0" y="0" width="100%" height="100%" fill="#f8fafc"/>')
    for p in layout['paths']:
        stroke_w = float(p.get('stroke_w', 2.25))
        opacity = float(p.get('opacity', 0.88))
        dash = str(p.get('dash', '')).strip()
        dash_attr = f' stroke-dasharray="{html_escape(dash)}"' if dash else ''
        out.append(
            f'<path d="{html_escape(p["d"])}" fill="none" stroke="{html_escape(p["stroke"])}" '
            f'stroke-width="{stroke_w:.2f}" stroke-linecap="round" opacity="{opacity:.2f}"{dash_attr}/>'
        )
    for n in layout['nodes']:
        left = int(n['left'])
        top = int(n['top'])
        node_w = int(n.get('width', layout['card_w']))
        node_h = int(n.get('height', layout['card_h']))
        task = n['task']
        completed = bool(task.get('is_completed'))
        title = str(task.get('title') or '')
        due = str(task.get('due_date') or '')
        assignee = str(task.get('assignee') or '')
        out.append(
            f'<rect x="{left}" y="{top}" width="{node_w}" height="{node_h}" rx="10" ry="10" '
            'fill="#ffffff" stroke="#cbd5e1" stroke-width="1"/>'
        )
        out.append(
            f'<rect x="{left}" y="{top}" width="{node_w}" height="4" rx="10" ry="10" '
            f'fill="{html_escape(str(n["accent"]))}"/>'
        )
        lines = _svg_text_lines(title)
        y = top + 22
        for ln in lines:
            out.append(
                f'<text x="{left + 10}" y="{y}" font-size="11" font-family="Arial, sans-serif" '
                f'fill="{"#94a3b8" if completed else "#0f172a"}">{html_escape(ln)}</text>'
            )
            y += 13
        meta = []
        if due:
            meta.append(f'Due: {due}')
        if assignee:
            meta.append(f'@{assignee}')
        if completed:
            meta.append('Done')
        meta_text = ' · '.join(meta) if meta else 'Open'
        out.append(
            f'<text x="{left + 10}" y="{top + node_h - 10}" font-size="10" '
            f'font-family="Arial, sans-serif" fill="#475569">{html_escape(meta_text)}</text>'
        )
    out.append('</svg>')
    return ''.join(out).encode('utf-8')


@method_decorator(ensure_csrf_cookie, name='dispatch')
class BoardView(LoginRequiredMixin, TemplateView):
    template_name = 'pages/board.jinja'
    login_url = reverse_lazy('users:login')

    def get(self, request, *args, **kwargs):
        mode = get_user_ui_mode(request.user)
        request.session.setdefault('task_layout', normalize_layout(mode, 'mindmap'))
        lay = request.GET.get('layout')
        if lay in ('tree', 'mindmap', 'mini', 'idea', 'kanban'):
            request.session['task_layout'] = normalize_layout(mode, lay)
            return redirect(request.path)
        return super().get(request, *args, **kwargs)

    def get_team(self):
        return _workspace_team(self.request.user, self.kwargs.get('team_slug'))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        team, project = _resolve_board(
            user,
            self.kwargs.get('team_slug'),
            self.kwargs.get('project_slug') or self.kwargs.get('slug'),
        )
        effective_team = team or (project.team if project else None)

        qs = _board_queryset(user, team, project)
        rows = task_rows_for_tree(qs)
        task_tree = build_task_tree(rows)
        layout = self.request.session.get('task_layout', 'mindmap')
        layout = normalize_layout(get_user_ui_mode(user), layout)
        if self.request.session.get('task_layout') != layout:
            self.request.session['task_layout'] = layout
        mm_collapsed = get_mindmap_collapsed_ids(
            self.request, team, project=project, tree=task_tree
        )
        focus_task_id: int | None = None
        raw_focus_task = (self.request.GET.get('focus_task') or '').strip()
        if raw_focus_task:
            try:
                requested_task_id = int(raw_focus_task)
            except ValueError:
                requested_task_id = 0
            if requested_task_id > 0:
                focus_task = qs.filter(pk=requested_task_id).first()
                if focus_task is not None:
                    focus_task_id = focus_task.id
                    keep_open_ids = _task_ancestor_ids(focus_task)
                    _set_tree_focus_expand_ids(self.request, keep_open_ids | {focus_task.id})
                    all_branch_ids = set(collect_branch_ids_with_children(task_tree))
                    set_mindmap_collapsed_ids(
                        self.request, team, all_branch_ids - keep_open_ids, project=project
                    )
                    mm_collapsed = get_mindmap_collapsed_ids(
                        self.request, team, project=project, tree=task_tree
                    )
        branch_children = collect_task_has_children(task_tree)
        pruned_for_mm = prune_mindmap_tree(task_tree, mm_collapsed)
        mindmap = (
            compute_mindmap_layout(
                pruned_for_mm,
                flow_style='natural',
                compact_mode=(layout == 'idea'),
            )
            if layout in ('mindmap', 'mini', 'idea')
            else None
        )
        flowmap = compute_mindmap_layout(task_tree, flow_style='relaxed') if layout == 'flow' else None
        total_main, done_main = root_stats(qs)
        u: WorkspaceUrls = workspace_urls(team, project)
        team_is_owner = False
        team_can_invite = False
        project_can_invite = False
        team_can_archive = False
        team_roster = []
        team_assignee_usernames = assignee_choices(
            actor=user, team=None if project else effective_team, project=project
        )
        if project:
            from projects.services import user_can_manage_project

            project_can_invite = user_can_manage_project(user, project)
        if team:
            try:
                has_team_plan = Profile.supports_team_plan(user.profile.plan)
            except Profile.DoesNotExist:
                has_team_plan = False
            team_is_owner = has_team_plan and TeamMembership.objects.filter(
                team=team, user=user, is_owner=True, is_active=True
            ).exists()
            membership = TeamMembership.objects.filter(team=team, user=user, is_active=True).first()
            team_can_invite = bool(membership and membership.can_manage_invites)
            team_can_archive = bool(membership)
            team_roster = list(
                TeamMembership.objects.filter(team=team, is_active=True)
                .select_related('user')
                .order_by('-is_owner', 'user__username')
            )
        invite_share = self.request.session.pop('invite_share', None)
        kanban_columns = None
        if layout == 'kanban':
            kanban_columns = _build_kanban_columns(qs)
        ctx.update(
            {
                'task_tree': task_tree,
                'task_layout': layout,
                'kanban_columns': kanban_columns,
                'mindmap': mindmap,
                'flowmap': flowmap,
                'mindmap_collapsed_ids': sorted(int(x) for x in mm_collapsed),
                'mindmap_branch_children': branch_children,
                'total_main': total_main,
                'done_main': done_main,
                'current_team': team,
                'current_project': project,
                'task_create_form': TaskCreateForm(),
                'task_import_form': TaskImportForm(),
                'team_create_form': TeamCreateForm(),
                'team_invite_form': TeamInviteForm(),
                'team_is_owner': team_is_owner,
                'team_can_invite': team_can_invite,
                'project_can_invite': project_can_invite,
                'team_can_archive': team_can_archive,
                'team_roster': team_roster,
                'team_assignee_usernames': team_assignee_usernames,
                'invite_share': invite_share,
                'tree_focus_expand_ids': _get_tree_focus_expand_ids(self.request),
                'focus_task_id': focus_task_id,
                'u': u,
                'is_tutorial_project': is_tutorial_project(project),
            }
        )
        return ctx


def _tree_partial(
    request,
    team_slug: str | None = None,
    project_slug: str | None = None,
    *,
    hx_triggers: bool = True,
):
    team, project = _resolve_board(request.user, team_slug, project_slug)
    effective_team = team or (project.team if project else None)
    qs, tree = _board_task_tree(request.user, team, project)
    layout = request.session.get('task_layout', 'mindmap')
    if layout not in ('tree', 'mindmap', 'mini', 'idea', 'kanban'):
        layout = 'mindmap'
    u = workspace_urls(team, project)
    team_assignee_usernames = assignee_choices(
        actor=request.user, team=None if project else effective_team, project=project
    )
    if layout in ('mindmap', 'mini', 'idea'):
        mm_collapsed = get_mindmap_collapsed_ids(request, team, project=project, tree=tree)
        branch_children = collect_task_has_children(tree)
        pruned = prune_mindmap_tree(tree, mm_collapsed)
        ctx = {
            'mindmap': compute_mindmap_layout(
                pruned,
                flow_style='natural',
                compact_mode=(layout == 'idea'),
            ),
            'task_tree': tree,
            'task_layout': layout,
            'mindmap_collapsed_ids': sorted(int(x) for x in mm_collapsed),
            'mindmap_branch_children': branch_children,
            'current_team': team,
            'current_project': project,
            'team_assignee_usernames': team_assignee_usernames,
            'tree_focus_expand_ids': _get_tree_focus_expand_ids(request),
            'u': u,
        }
        tmpl = 'partials/task_mindmap.jinja'
    elif layout == 'kanban':
        ctx = {
            'task_tree': tree,
            'task_layout': layout,
            'kanban_columns': _build_kanban_columns(qs),
            'current_team': team,
            'current_project': project,
            'team_assignee_usernames': team_assignee_usernames,
            'u': u,
        }
        tmpl = 'partials/task_kanban.jinja'
    else:
        ctx = {
            'task_tree': tree,
            'task_layout': layout,
            'current_team': team,
            'current_project': project,
            'team_assignee_usernames': team_assignee_usernames,
            'tree_focus_expand_ids': _get_tree_focus_expand_ids(request),
            'u': u,
        }
        tmpl = 'partials/task_tree.jinja'
    html = render(request, tmpl, ctx).content.decode()
    resp = HttpResponse(html)
    resp['Cache-Control'] = 'no-store, max-age=0'
    if hx_triggers:
        trigger_payload: dict[str, object] = {
            'updateStats': True,
            'refreshMyTasks': True,
        }
        if team is not None:
            pct = workspace_root_average_percent(qs)
            trigger_payload['sidebarTeamPct'] = {'teamId': team.id, 'pct': pct}
        resp['HX-Trigger'] = json.dumps(trigger_payload)
    return resp


class MindmapCollapseToggleView(LoginRequiredMixin, View):
    """Toggle collapsed branch in mind map (session, per workspace)."""

    def post(self, request, task_id, team_slug=None, project_slug=None, slug=None):
        project_slug = project_slug or slug
        team, project = _resolve_board(request.user, team_slug, project_slug)
        task = Task.objects.filter(pk=task_id).only('id', 'parent_id', 'project_id', 'team_id').first()
        if task is None or not user_can_access_task(request.user, task, team):
            return HttpResponse('Not found', status=404)
        _, tree = _board_task_tree(request.user, team, project)
        tid = int(task_id)
        branch_children = collect_task_has_children(tree)
        if not branch_children.get(tid):
            return HttpResponse('No subtasks', status=400)
        cur = get_mindmap_collapsed_ids(request, team, project=project, tree=tree)
        if tid in cur:
            cur.discard(tid)
            cur.update(_direct_branch_child_ids(tree, tid))
        else:
            cur.add(tid)
        set_mindmap_collapsed_ids(request, team, cur, project=project)
        return _tree_partial(request, team_slug, project_slug, hx_triggers=False)


class MindmapCollapseAllView(LoginRequiredMixin, View):
    """Collapse all branches in the mind map."""

    def post(self, request, team_slug=None, project_slug=None, slug=None):
        project_slug = project_slug or slug
        team, project = _resolve_board(request.user, team_slug, project_slug)
        _, tree = _board_task_tree(request.user, team, project)
        all_branch_ids = set(collect_branch_ids_with_children(tree))
        set_mindmap_collapsed_ids(request, team, all_branch_ids, project=project)
        return _tree_partial(request, team_slug, project_slug, hx_triggers=False)


class MindmapExpandAllView(LoginRequiredMixin, View):
    """Expand all branches in the mind map."""

    def post(self, request, team_slug=None, project_slug=None, slug=None):
        project_slug = project_slug or slug
        team, project = _resolve_board(request.user, team_slug, project_slug)
        set_mindmap_collapsed_ids(request, team, set(), project=project)
        return _tree_partial(request, team_slug, project_slug, hx_triggers=False)


class TaskCreateView(LoginRequiredMixin, View):
    def post(self, request, team_slug=None, project_slug=None, slug=None):
        project_slug = project_slug or slug
        team, project = _resolve_board(request.user, team_slug, project_slug)
        form = TaskCreateForm(request.POST)
        template = (request.POST.get('template') or '').strip().lower()
        use_99d = template == '99d' and not (request.POST.get('parent_id') or '').strip()

        if use_99d:
            title = (request.POST.get('title') or '').strip()
            if title in {'99D', '33D', '11D'}:
                title = ''
            due_raw = (request.POST.get('due_date') or '').strip()
            due_date = None
            if due_raw:
                from datetime import datetime
                try:
                    due_date = datetime.strptime(due_raw, '%Y-%m-%d').date()
                except ValueError:
                    return HttpResponse('Invalid date', status=400)
            assignee_username = (request.POST.get('assignee_username') or '').strip()
            effective_team = team or (project.team if project else None)
            assignee_username, assignee_error = _validate_assignee_for_workspace(
                actor=request.user,
                team=effective_team,
                assignee_username=assignee_username,
                project=project,
            )
            if assignee_error:
                return HttpResponse(assignee_error, status=400)
            task = create_99d_template(
                author=request.user,
                team=effective_team,
                project=project,
                due_date=due_date,
                assignee_username=assignee_username,
                root_title=title,
            )
            _maybe_update_project_progress(task)
            qs = _board_queryset(request.user, team, project)
            rows = task_rows_for_tree(qs)
            tree = build_task_tree(rows)
            branch_ids = set(collect_branch_ids_with_children(tree))
            # Keep 99D + its 33D branches expanded so the starter tree is visible.
            keep_open_ids = {task.id} | set(
                Task.objects.filter(parent_id=task.id).values_list('id', flat=True)
            )
            _set_tree_focus_expand_ids(request, keep_open_ids)
            set_mindmap_collapsed_ids(request, team, branch_ids - keep_open_ids, project=project)
            notify_assignee(
                assignee_username=assignee_username,
                actor=request.user,
                title=task.title_plain,
                old_assignee='',
            )
            response = _tree_partial(request, team_slug, project_slug)
            trigger_payload: dict[str, object] = {
                'updateStats': True,
                'taskCreated': {'taskId': task.id},
            }
            if team is not None:
                pct = workspace_root_average_percent(qs)
                trigger_payload['sidebarTeamPct'] = {'teamId': team.id, 'pct': pct}
            response['HX-Trigger'] = json.dumps(trigger_payload)
            return response

        if not form.is_valid():
            return HttpResponse('Invalid', status=400)
        parent_id = request.POST.get('parent_id') or None
        parent = None
        if parent_id:
            try:
                pid = int(parent_id)
            except ValueError:
                return HttpResponse('Bad parent', status=400)
            parent = Task.objects.filter(pk=pid).first()
            if parent is None or not user_can_access_task(request.user, parent, team):
                return HttpResponse('Not found', status=404)
            if project and parent.project_id != project.id:
                return HttpResponse('Not found', status=404)
            if not project:
                if team is None and parent.team_id is not None:
                    return HttpResponse('Not found', status=404)
                if team is not None and parent.team_id != team.id:
                    return HttpResponse('Not found', status=404)

        task = form.save(commit=False)
        effective_team = team or (project.team if project else None)
        canonical, assignee_error = _validate_assignee_for_workspace(
            actor=request.user,
            team=effective_team,
            assignee_username=task.assignee_username,
            project=project,
        )
        if assignee_error:
            return HttpResponse(assignee_error, status=400)
        task.assignee_username = canonical
        task.author = request.user
        task.project = project
        task.team = effective_team
        task.parent = parent
        task.save()
        _maybe_update_project_progress(task)
        # New child can change parent completion status (e.g. completed parent gets a new open child).
        sync_parent_completion_from_children(task.parent)
        # Keep only the new task path expanded in mind map; collapse other branches.
        qs = _board_queryset(request.user, team, project)
        rows = task_rows_for_tree(qs)
        tree = build_task_tree(rows)
        branch_ids = set(collect_branch_ids_with_children(tree))
        keep_open_ids: set[int] = set()
        cur = task
        while cur.parent_id is not None:
            keep_open_ids.add(cur.parent_id)
            cur = cur.parent
        _set_tree_focus_expand_ids(request, keep_open_ids | {task.id})
        set_mindmap_collapsed_ids(request, team, branch_ids - keep_open_ids, project=project)
        notify_assignee(
            assignee_username=(task.assignee_username or '').strip(),
            actor=request.user,
            title=task.title_plain,
            old_assignee='',
        )
        response = _tree_partial(request, team_slug, project_slug)
        trigger_payload: dict[str, object] = {
            'updateStats': True,
            'taskCreated': {'taskId': task.id},
        }
        if team is not None:
            pct = workspace_root_average_percent(qs)
            trigger_payload['sidebarTeamPct'] = {'teamId': team.id, 'pct': pct}
        response['HX-Trigger'] = json.dumps(
            trigger_payload
        )
        return response


class TaskImportView(LoginRequiredMixin, View):
    def post(self, request, team_slug=None):
        team = _workspace_team(request.user, team_slug)
        if team_slug and team is None:
            return HttpResponse('Not found', status=404)
        form = TaskImportForm(request.POST, request.FILES)
        if not form.is_valid():
            return HttpResponse('Upload a valid .csv or .txt file', status=400)
        try:
            import_tasks_from_upload(
                uploaded_file=form.cleaned_data['file'],
                author=request.user,
                team=team,
            )
        except ValueError as e:
            return HttpResponse(str(e), status=400)
        return _tree_partial(request, team_slug)


class TaskToggleView(LoginRequiredMixin, View):
    def post(self, request, task_id, team_slug=None, project_slug=None, slug=None):
        project_slug = project_slug or slug
        team, project = _resolve_board(request.user, team_slug, project_slug)
        task = get_object_or_404(Task, pk=task_id)
        if not user_can_access_task(request.user, task, team):
            return HttpResponse('Not found', status=404)
        task.is_completed = not task.is_completed
        _sync_task_completion_fields(task)
        task.save(update_fields=['is_completed', 'status'])
        # Keep branch behavior consistent: toggling a parent cascades to all descendants.
        sync_descendant_completion(task, task.is_completed)
        # Propagate completion consistency upward through all ancestors.
        sync_parent_completion_from_children(task.parent)
        _maybe_update_project_progress(task)
        return _tree_partial(request, team_slug, project_slug)


class TaskDeleteView(LoginRequiredMixin, View):
    def delete(self, request, task_id, team_slug=None, project_slug=None, slug=None):
        project_slug = project_slug or slug
        team, project = _resolve_board(request.user, team_slug, project_slug)
        task = get_object_or_404(Task, pk=task_id)
        if not user_can_access_task(request.user, task, team):
            return HttpResponse('Not found', status=404)
        project_ref = task.project
        parent = task.parent
        task.delete()
        # Deleting a child can complete/reopen ancestor branches.
        sync_parent_completion_from_children(parent)
        if project_ref:
            from projects.services import update_project_progress

            update_project_progress(project_ref)
        return _tree_partial(request, team_slug, project_slug)


class TaskRenameView(LoginRequiredMixin, View):
    def post(self, request, task_id, team_slug=None, project_slug=None, slug=None):
        project_slug = project_slug or slug
        team, project = _resolve_board(request.user, team_slug, project_slug)
        task = get_object_or_404(Task, pk=task_id)
        if not user_can_access_task(request.user, task, team):
            return HttpResponse('Not found', status=404)
        form = TaskTitleForm(request.POST)
        if not form.is_valid():
            return HttpResponse('Invalid title', status=400)
        task.title = form.cleaned_data['title'].strip()
        # Allow clearing badge-default labels (99D / 33D / 11D) to empty.
        if task.title in {'99D', '33D', '11D'}:
            task.title = ''
        task.save(update_fields=['title'])
        return _tree_partial(request, team_slug, project_slug)


class TaskMetaView(LoginRequiredMixin, View):
    def post(self, request, task_id, team_slug=None, project_slug=None, slug=None):
        project_slug = project_slug or slug
        team, project = _resolve_board(request.user, team_slug, project_slug)
        task = get_object_or_404(Task, pk=task_id)
        if not user_can_access_task(request.user, task, team):
            return HttpResponse('Not found', status=404)
        form = TaskMetaForm(request.POST)
        if not form.is_valid():
            return HttpResponse('Invalid', status=400)
        old = task.assignee_username or ''
        new_assignee = (form.cleaned_data.get('assignee_username') or '').strip()
        effective_team = team or (project.team if project else None)
        canonical, assignee_error = _validate_assignee_for_workspace(
            actor=request.user,
            team=effective_team,
            assignee_username=new_assignee,
            project=project,
        )
        if assignee_error:
            return HttpResponse(assignee_error, status=400)
        task.due_date = form.cleaned_data.get('due_date')
        task.assignee_username = canonical
        task.save(update_fields=['due_date', 'assignee_username'])
        notify_assignee(
            assignee_username=task.assignee_username,
            actor=request.user,
            title=task.title_plain,
            old_assignee=old,
        )
        return _tree_partial(request, team_slug, project_slug)


class StatsPartialView(LoginRequiredMixin, View):
    def get(self, request, team_slug=None, project_slug=None, slug=None):
        project_slug = project_slug or slug
        team, project = _resolve_board(request.user, team_slug, project_slug)
        qs = _board_queryset(request.user, team, project)
        total_main, done_main = root_stats(qs)
        return render(
            request,
            'partials/stats.jinja',
            {'total_main': total_main, 'done_main': done_main},
        )


class SidebarMyTasksPartialView(LoginRequiredMixin, View):
    """HTMX fragment: assigned open tasks for sidebar (keeps list in sync after toggles)."""

    def get(self, request):
        chrome = workspace_chrome(request)
        tasks = chrome.get('my_assigned_tasks')
        if tasks is None:
            tasks = []
        return render(
            request,
            'partials/sidebar_my_tasks_list.jinja',
            {'my_assigned_tasks': tasks},
        )


class TaskTreePartialView(LoginRequiredMixin, View):
    def get(self, request, team_slug=None, project_slug=None, slug=None):
        project_slug = project_slug or slug
        return _tree_partial(request, team_slug, project_slug)


class NotificationReadView(LoginRequiredMixin, View):
    def post(self, request, n_id):
        Notification.objects.filter(pk=n_id, user=request.user).update(is_read=True)
        return HttpResponse('')


class TeamMindmapArchiveView(LoginRequiredMixin, View):
    """Archive all tasks in a team workspace without deleting data."""

    def post(self, request, team_slug):
        team = _workspace_team(request.user, team_slug)
        if team is None:
            return HttpResponse('Not found', status=404)
        membership = TeamMembership.objects.filter(
            team=team, user=request.user, is_active=True
        ).first()
        if not membership:
            return HttpResponse('Only team members can archive team mindmap', status=403)
        archived = Task.objects.filter(team=team, is_archived=False).update(is_archived=True)
        if archived:
            messages.success(request, f'Archived {archived} team task(s) from {team.name}.')
        else:
            messages.info(request, f'No active tasks to archive in {team.name}.')
        return redirect('planner:board_team', team_slug=team.slug)


class TeamMindmapUnarchiveView(LoginRequiredMixin, View):
    """Restore archived tasks for a team workspace."""

    def post(self, request, team_slug):
        team = _workspace_team(request.user, team_slug)
        if team is None:
            return HttpResponse('Not found', status=404)
        membership = TeamMembership.objects.filter(
            team=team, user=request.user, is_active=True
        ).first()
        if not membership:
            return HttpResponse('Only team members can unarchive team mindmap', status=403)
        restored = Task.objects.filter(team=team, is_archived=True).update(is_archived=False)
        if restored:
            messages.success(request, f'Restored {restored} archived task(s) in {team.name}.')
        else:
            messages.info(request, f'No archived tasks found for {team.name}.')
        return redirect('billing:overview')


class TaskExportCsvView(LoginRequiredMixin, View):
    """Export workspace tasks as CSV for Excel / Google Sheets."""

    def get(self, request, team_slug=None):
        team = _workspace_team(request.user, team_slug)
        if team_slug and team is None:
            return HttpResponse('Not found', status=404)
        qs = tasks_for_workspace(request.user, team).select_related('author', 'team', 'parent')
        response = HttpResponse(content_type='text/csv')
        workspace = team.slug if team else 'personal'
        response['Content-Disposition'] = f'attachment; filename="tasks-{workspace}.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
                'task_id',
                'title',
                'is_completed',
                'due_date',
                'assignee_username',
                'author_username',
                'team_slug',
                'parent_task_id',
            ]
        )
        for task in qs:
            writer.writerow(
                [
                    task.id,
                    decrypt_task_title(task.title),
                    'yes' if task.is_completed else 'no',
                    task.due_date.isoformat() if task.due_date else '',
                    task.assignee_username or '',
                    task.author.username,
                    task.team.slug if task.team else '',
                    task.parent_id or '',
                ]
            )
        return response


class MindmapExportView(LoginRequiredMixin, View):
    """Export current workspace mindmap as PNG/PDF/SVG."""

    def get(self, request, team_slug=None):
        team = _workspace_team(request.user, team_slug)
        if team_slug and team is None:
            return HttpResponse('Not found', status=404)
        export_format = (request.GET.get('format') or 'png').strip().lower()
        if export_format not in {'png', 'pdf', 'svg'}:
            return HttpResponse('Invalid export format', status=400)
        qs = tasks_for_workspace(request.user, team)
        rows = task_rows_for_tree(qs)
        tree = build_task_tree(rows)
        svg_bytes = _mindmap_svg_bytes(tree=tree, flow_style='natural')
        workspace = team.slug if team else 'personal'
        if export_format == 'svg':
            response = HttpResponse(svg_bytes, content_type='image/svg+xml')
            response['Content-Disposition'] = (
                f'attachment; filename="mindmap-{workspace}.svg"'
            )
            return response
        try:
            import cairosvg  # noqa: PLC0415
        except ImportError:
            return HttpResponse('Install cairosvg to enable PNG/PDF exports', status=503)
        try:
            if export_format == 'png':
                png_bytes = cairosvg.svg2png(bytestring=svg_bytes)
                response = HttpResponse(png_bytes, content_type='image/png')
                response['Content-Disposition'] = (
                    f'attachment; filename="mindmap-{workspace}.png"'
                )
                return response
            pdf_bytes = cairosvg.svg2pdf(bytestring=svg_bytes)
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = (
                f'attachment; filename="mindmap-{workspace}.pdf"'
            )
            return response
        except Exception:
            # Common in slim Docker images when system Cairo libs are missing.
            return HttpResponse(
                'PDF export engine unavailable. Install Cairo libs in Docker and rebuild web image.',
                status=503,
            )


def _build_kanban_columns(qs):
    from planner.models import Task as TaskModel
    columns = [
        {'key': TaskModel.STATUS_TODO, 'label': 'To Do', 'color': 'slate'},
        {'key': TaskModel.STATUS_IN_PROGRESS, 'label': 'In Progress', 'color': 'blue'},
        {'key': TaskModel.STATUS_REVIEW, 'label': 'Review', 'color': 'purple'},
        {'key': TaskModel.STATUS_TESTING, 'label': 'Testing', 'color': 'orange'},
        {'key': TaskModel.STATUS_DONE, 'label': 'Done', 'color': 'green'},
    ]
    # Only root tasks (no parent) for kanban
    root_qs = qs.filter(parent__isnull=True).order_by('position', 'id')
    tasks_by_status = {}
    for task in root_qs:
        s = task.status if task.status else TaskModel.STATUS_TODO
        tasks_by_status.setdefault(s, []).append(task)
    for col in columns:
        col['tasks'] = tasks_by_status.get(col['key'], [])
    return columns


class TaskKanbanStatusView(LoginRequiredMixin, View):
    """HTMX POST: update task status from kanban drag-drop."""
    login_url = reverse_lazy('users:login')

    def post(self, request, task_id, team_slug=None, project_slug=None):
        from planner.models import Task as TaskModel

        team, project = _resolve_board(request.user, team_slug, project_slug)
        task = get_object_or_404(TaskModel, pk=task_id)
        if not user_can_access_task(request.user, task, team):
            return HttpResponse(status=403)
        new_status = request.POST.get('status', '')
        valid = [c[0] for c in TaskModel.STATUS_CHOICES]
        if new_status not in valid:
            return HttpResponse(status=400)
        task.status = new_status
        if new_status == TaskModel.STATUS_DONE:
            task.is_completed = True
        elif task.is_completed:
            task.is_completed = False
        task.save(update_fields=['status', 'is_completed'])
        sync_parent_completion_from_children(task.parent)
        _maybe_update_project_progress(task)
        return HttpResponse(status=204, headers={'HX-Trigger': 'refreshKanban'})


# ── Task Detail Panel ─────────────────────────────────────────────────────────

def _task_detail_ctx(task):
    from planner.models import TaskComment, TaskChecklist
    comments = list(task.comments.select_related('author').order_by('created_at'))
    checklist = list(task.checklist_items.order_by('position', 'id'))
    done_count = sum(1 for i in checklist if i.is_done)
    return {
        'task': task,
        'comments': comments,
        'checklist': checklist,
        'done_count': done_count,
        'total_count': len(checklist),
    }


class TaskDetailModalView(LoginRequiredMixin, View):
    login_url = reverse_lazy('users:login')

    def get(self, request, task_id):
        task = get_object_or_404(Task, pk=task_id)
        if not user_can_access_task(request.user, task):
            return HttpResponse(status=403)
        return render(request, 'partials/_task_detail.jinja', _task_detail_ctx(task))


class TaskCommentCreateView(LoginRequiredMixin, View):
    login_url = reverse_lazy('users:login')

    def post(self, request, task_id):
        from planner.models import TaskComment
        task = get_object_or_404(Task, pk=task_id)
        if not user_can_access_task(request.user, task):
            return HttpResponse(status=403)
        body = request.POST.get('body', '').strip()
        if not body:
            return HttpResponse(status=400)
        TaskComment.objects.create(task=task, author=request.user, body=body)
        comments = list(task.comments.select_related('author').order_by('created_at'))
        return render(request, 'partials/_task_comments.jinja', {'task': task, 'comments': comments})


class TaskCommentDeleteView(LoginRequiredMixin, View):
    login_url = reverse_lazy('users:login')

    def post(self, request, task_id, comment_id):
        from planner.models import TaskComment
        comment = get_object_or_404(TaskComment, pk=comment_id, task_id=task_id)
        if comment.author != request.user and not request.user.is_staff:
            return HttpResponse(status=403)
        task = comment.task
        comment.delete()
        comments = list(task.comments.select_related('author').order_by('created_at'))
        return render(request, 'partials/_task_comments.jinja', {'task': task, 'comments': comments})


class TaskChecklistCreateView(LoginRequiredMixin, View):
    login_url = reverse_lazy('users:login')

    def post(self, request, task_id):
        from planner.models import TaskChecklist
        from django.db.models import Max
        task = get_object_or_404(Task, pk=task_id)
        if not user_can_access_task(request.user, task):
            return HttpResponse(status=403)
        text = request.POST.get('text', '').strip()
        if not text:
            return HttpResponse(status=400)
        max_pos = task.checklist_items.aggregate(m=Max('position'))['m'] or 0
        TaskChecklist.objects.create(task=task, text=text, position=max_pos + 1)
        return _render_checklist(request, task)


class TaskChecklistToggleView(LoginRequiredMixin, View):
    login_url = reverse_lazy('users:login')

    def post(self, request, task_id, item_id):
        from planner.models import TaskChecklist
        item = get_object_or_404(TaskChecklist, pk=item_id, task_id=task_id)
        if not user_can_access_task(request.user, item.task):
            return HttpResponse(status=403)
        item.is_done = not item.is_done
        item.save(update_fields=['is_done'])
        return _render_checklist(request, item.task)


class TaskChecklistDeleteView(LoginRequiredMixin, View):
    login_url = reverse_lazy('users:login')

    def post(self, request, task_id, item_id):
        from planner.models import TaskChecklist
        item = get_object_or_404(TaskChecklist, pk=item_id, task_id=task_id)
        if not user_can_access_task(request.user, item.task):
            return HttpResponse(status=403)
        task = item.task
        item.delete()
        return _render_checklist(request, task)


def _render_checklist(request, task):
    checklist = list(task.checklist_items.order_by('position', 'id'))
    done_count = sum(1 for i in checklist if i.is_done)
    return render(request, 'partials/_task_checklist.jinja', {
        'task': task,
        'checklist': checklist,
        'done_count': done_count,
        'total_count': len(checklist),
    })
