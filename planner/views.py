import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import TemplateView

from planner.forms import TaskCreateForm, TaskImportForm, TaskMetaForm, TaskTitleForm
from planner.models import Notification, Task
from planner.services import (
    build_task_tree,
    collect_branch_ids_with_children,
    collect_task_has_children,
    compute_mindmap_layout,
    get_mindmap_collapsed_ids,
    import_tasks_from_upload,
    notify_assignee,
    prune_mindmap_tree,
    root_stats,
    set_mindmap_collapsed_ids,
    task_rows_for_tree,
    tasks_for_workspace,
    user_can_access_task,
)
from teams.forms import TeamCreateForm, TeamInviteForm
from teams.models import Team, TeamMembership
from users.models import Profile


class WorkspaceUrls:
    __slots__ = ('_slug',)

    def __init__(self, team: Team | None):
        self._slug = team.slug if team else None

    @property
    def stats(self) -> str:
        if self._slug:
            return reverse('planner:stats_team', kwargs={'team_slug': self._slug})
        return reverse('planner:stats_personal')

    @property
    def tasks(self) -> str:
        if self._slug:
            return reverse('planner:task_create_team', kwargs={'team_slug': self._slug})
        return reverse('planner:task_create_personal')

    @property
    def task_import(self) -> str:
        if self._slug:
            return reverse('planner:task_import_team', kwargs={'team_slug': self._slug})
        return reverse('planner:task_import_personal')

    def toggle(self, task_id: int) -> str:
        if self._slug:
            return reverse(
                'planner:task_toggle_team',
                kwargs={'team_slug': self._slug, 'task_id': task_id},
            )
        return reverse('planner:task_toggle_personal', kwargs={'task_id': task_id})

    def delete(self, task_id: int) -> str:
        if self._slug:
            return reverse(
                'planner:task_delete_team',
                kwargs={'team_slug': self._slug, 'task_id': task_id},
            )
        return reverse('planner:task_delete_personal', kwargs={'task_id': task_id})

    def title(self, task_id: int) -> str:
        if self._slug:
            return reverse(
                'planner:task_title_team',
                kwargs={'team_slug': self._slug, 'task_id': task_id},
            )
        return reverse('planner:task_title_personal', kwargs={'task_id': task_id})

    def meta(self, task_id: int) -> str:
        if self._slug:
            return reverse(
                'planner:task_meta_team',
                kwargs={'team_slug': self._slug, 'task_id': task_id},
            )
        return reverse('planner:task_meta_personal', kwargs={'task_id': task_id})

    def mindmap_collapse(self, task_id: int) -> str:
        if self._slug:
            return reverse(
                'planner:mindmap_collapse_team',
                kwargs={'team_slug': self._slug, 'task_id': task_id},
            )
        return reverse('planner:mindmap_collapse_personal', kwargs={'task_id': task_id})


def workspace_urls(team: Team | None) -> WorkspaceUrls:
    return WorkspaceUrls(team)


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
    if not TeamMembership.objects.filter(team=team, user=user).exists():
        return None
    return team


class BoardView(LoginRequiredMixin, TemplateView):
    template_name = 'pages/board.jinja'
    login_url = reverse_lazy('users:login')

    def get(self, request, *args, **kwargs):
        request.session.setdefault('task_layout', 'mindmap')
        lay = request.GET.get('layout')
        if lay in ('tree', 'mindmap'):
            request.session['task_layout'] = lay
            return redirect(request.path)
        return super().get(request, *args, **kwargs)

    def get_team(self):
        return _workspace_team(self.request.user, self.kwargs.get('team_slug'))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        team = self.get_team()
        if self.kwargs.get('team_slug') and team is None:
            raise Http404('Team not found')

        qs = tasks_for_workspace(user, team)
        rows = task_rows_for_tree(qs)
        task_tree = build_task_tree(rows)
        layout = self.request.session.get('task_layout', 'mindmap')
        if layout not in ('tree', 'mindmap'):
            layout = 'mindmap'
        mm_collapsed = get_mindmap_collapsed_ids(
            self.request, team, tree=task_tree
        )
        branch_children = collect_task_has_children(task_tree)
        pruned_for_mm = prune_mindmap_tree(task_tree, mm_collapsed)
        mindmap = (
            compute_mindmap_layout(pruned_for_mm) if layout == 'mindmap' else None
        )
        total_main, done_main = root_stats(qs)
        u: WorkspaceUrls = workspace_urls(team)
        team_is_owner = False
        team_roster = []
        if team:
            try:
                has_team_plan = user.profile.plan == Profile.PLAN_TEAM
            except Profile.DoesNotExist:
                has_team_plan = False
            team_is_owner = has_team_plan and TeamMembership.objects.filter(
                team=team, user=user, is_owner=True
            ).exists()
            team_roster = list(
                TeamMembership.objects.filter(team=team)
                .select_related('user')
                .order_by('-is_owner', 'user__username')
            )
        ctx.update(
            {
                'task_tree': task_tree,
                'task_layout': layout,
                'mindmap': mindmap,
                'mindmap_collapsed_ids': sorted(mm_collapsed),
                'mindmap_branch_children': branch_children,
                'total_main': total_main,
                'done_main': done_main,
                'current_team': team,
                'task_create_form': TaskCreateForm(),
                'task_import_form': TaskImportForm(),
                'team_create_form': TeamCreateForm(),
                'team_invite_form': TeamInviteForm(),
                'team_is_owner': team_is_owner,
                'team_roster': team_roster,
                'tree_focus_expand_ids': _get_tree_focus_expand_ids(self.request),
                'u': u,
            }
        )
        return ctx


def _tree_partial(request, team_slug: str | None):
    team = _workspace_team(request.user, team_slug)
    if team_slug and team is None:
        return HttpResponse('Not found', status=404)
    qs = tasks_for_workspace(request.user, team)
    rows = task_rows_for_tree(qs)
    tree = build_task_tree(rows)
    layout = request.session.get('task_layout', 'mindmap')
    if layout not in ('tree', 'mindmap'):
        layout = 'mindmap'
    u = workspace_urls(team)
    if layout == 'mindmap':
        mm_collapsed = get_mindmap_collapsed_ids(request, team, tree=tree)
        branch_children = collect_task_has_children(tree)
        pruned = prune_mindmap_tree(tree, mm_collapsed)
        ctx = {
            'mindmap': compute_mindmap_layout(pruned),
            'task_tree': tree,
            'mindmap_collapsed_ids': sorted(mm_collapsed),
            'mindmap_branch_children': branch_children,
            'current_team': team,
            'tree_focus_expand_ids': _get_tree_focus_expand_ids(request),
            'u': u,
        }
        tmpl = 'partials/task_mindmap.jinja'
    else:
        ctx = {
            'task_tree': tree,
            'current_team': team,
            'tree_focus_expand_ids': _get_tree_focus_expand_ids(request),
            'u': u,
        }
        tmpl = 'partials/task_tree.jinja'
    html = render(request, tmpl, ctx).content.decode()
    resp = HttpResponse(html)
    resp['HX-Trigger'] = 'updateStats'
    return resp


class MindmapCollapseToggleView(LoginRequiredMixin, View):
    """Toggle collapsed branch in mind map (session, per workspace)."""

    def post(self, request, task_id, team_slug=None):
        team = _workspace_team(request.user, team_slug)
        if team_slug and team is None:
            return HttpResponse('Not found', status=404)
        task = Task.objects.filter(pk=task_id).first()
        if task is None or not user_can_access_task(request.user, task, team):
            return HttpResponse('Not found', status=404)
        has_kids = Task.objects.filter(parent_id=task_id).exists()
        if not has_kids:
            return HttpResponse('No subtasks', status=400)
        qs = tasks_for_workspace(request.user, team)
        rows = task_rows_for_tree(qs)
        tree = build_task_tree(rows)
        cur = get_mindmap_collapsed_ids(request, team, tree=tree)
        tid = int(task_id)
        if tid in cur:
            cur.discard(tid)
        else:
            cur.add(tid)
        set_mindmap_collapsed_ids(request, team, cur)
        return _tree_partial(request, team_slug)


class TaskCreateView(LoginRequiredMixin, View):
    def post(self, request, team_slug=None):
        team = _workspace_team(request.user, team_slug)
        if team_slug and team is None:
            return HttpResponse('Not found', status=404)
        form = TaskCreateForm(request.POST)
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
            if team is None and parent.team_id is not None:
                return HttpResponse('Not found', status=404)
            if team is not None and parent.team_id != team.id:
                return HttpResponse('Not found', status=404)

        task = form.save(commit=False)
        task.author = request.user
        task.team = team
        task.parent = parent
        task.save()
        # Keep only the new task path expanded in mind map; collapse other branches.
        qs = tasks_for_workspace(request.user, team)
        rows = task_rows_for_tree(qs)
        tree = build_task_tree(rows)
        branch_ids = set(collect_branch_ids_with_children(tree))
        keep_open_ids: set[int] = set()
        cur = task
        while cur.parent_id is not None:
            keep_open_ids.add(cur.parent_id)
            cur = cur.parent
        _set_tree_focus_expand_ids(request, keep_open_ids | {task.id})
        set_mindmap_collapsed_ids(request, team, branch_ids - keep_open_ids)
        notify_assignee(
            assignee_username=(task.assignee_username or '').strip(),
            actor=request.user,
            title=task.title,
            old_assignee='',
        )
        response = _tree_partial(request, team_slug)
        response['HX-Trigger'] = json.dumps(
            {
                'updateStats': True,
                'taskCreated': {'taskId': task.id},
            }
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
    def post(self, request, task_id, team_slug=None):
        team = _workspace_team(request.user, team_slug)
        if team_slug and team is None:
            return HttpResponse('Not found', status=404)
        task = get_object_or_404(Task, pk=task_id)
        if not user_can_access_task(request.user, task, team):
            return HttpResponse('Not found', status=404)
        task.is_completed = not task.is_completed
        task.save(update_fields=['is_completed'])
        return _tree_partial(request, team_slug)


class TaskDeleteView(LoginRequiredMixin, View):
    def delete(self, request, task_id, team_slug=None):
        team = _workspace_team(request.user, team_slug)
        if team_slug and team is None:
            return HttpResponse('Not found', status=404)
        task = get_object_or_404(Task, pk=task_id)
        if not user_can_access_task(request.user, task, team):
            return HttpResponse('Not found', status=404)
        task.delete()
        return _tree_partial(request, team_slug)


class TaskRenameView(LoginRequiredMixin, View):
    def post(self, request, task_id, team_slug=None):
        team = _workspace_team(request.user, team_slug)
        if team_slug and team is None:
            return HttpResponse('Not found', status=404)
        task = get_object_or_404(Task, pk=task_id)
        if not user_can_access_task(request.user, task, team):
            return HttpResponse('Not found', status=404)
        form = TaskTitleForm(request.POST)
        if not form.is_valid():
            return HttpResponse('Title required', status=400)
        task.title = form.cleaned_data['title'].strip()
        if not task.title:
            return HttpResponse('Title required', status=400)
        task.save(update_fields=['title'])
        return _tree_partial(request, team_slug)


class TaskMetaView(LoginRequiredMixin, View):
    def post(self, request, task_id, team_slug=None):
        team = _workspace_team(request.user, team_slug)
        if team_slug and team is None:
            return HttpResponse('Not found', status=404)
        task = get_object_or_404(Task, pk=task_id)
        if not user_can_access_task(request.user, task, team):
            return HttpResponse('Not found', status=404)
        form = TaskMetaForm(request.POST)
        if not form.is_valid():
            return HttpResponse('Invalid', status=400)
        old = task.assignee_username or ''
        task.due_date = form.cleaned_data.get('due_date')
        task.assignee_username = (form.cleaned_data.get('assignee_username') or '').strip()
        task.save(update_fields=['due_date', 'assignee_username'])
        notify_assignee(
            assignee_username=task.assignee_username,
            actor=request.user,
            title=task.title,
            old_assignee=old,
        )
        return _tree_partial(request, team_slug)


class StatsPartialView(LoginRequiredMixin, View):
    def get(self, request, team_slug=None):
        team = _workspace_team(request.user, team_slug)
        if team_slug and team is None:
            return HttpResponse('Not found', status=404)
        qs = tasks_for_workspace(request.user, team)
        total_main, done_main = root_stats(qs)
        return render(
            request,
            'partials/stats.jinja',
            {'total_main': total_main, 'done_main': done_main},
        )


class NotificationReadView(LoginRequiredMixin, View):
    def post(self, request, n_id):
        Notification.objects.filter(pk=n_id, user=request.user).update(is_read=True)
        return HttpResponse('')
