from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView

from milestones.forms import MilestoneForm
from milestones.models import Milestone
from projects.models import Project
from projects.services import get_user_projects, user_can_access_project, user_can_manage_project


class MilestoneListView(LoginRequiredMixin, TemplateView):
    template_name = 'milestones/list.jinja'

    def dispatch(self, request, *args, **kwargs):
        project = get_object_or_404(Project, slug=kwargs['slug'])
        if not user_can_access_project(request.user, project):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        project = get_object_or_404(Project, slug=kwargs['slug'])
        ctx['project'] = project
        ctx['milestones'] = project.milestones.all()
        ctx['can_manage'] = user_can_manage_project(self.request.user, project)
        ctx['form'] = MilestoneForm()
        return ctx


class MilestoneCreateView(LoginRequiredMixin, View):
    def post(self, request, slug):
        project = get_object_or_404(Project, slug=slug)
        if not user_can_manage_project(request.user, project):
            return HttpResponse(status=403)
        form = MilestoneForm(request.POST)
        if form.is_valid():
            ms = form.save(commit=False)
            ms.project = project
            ms.created_by = request.user
            ms.save()
            if request.headers.get('HX-Request'):
                from django.template.loader import render_to_string
                html = render_to_string('milestones/_milestone_row.jinja', {'ms': ms, 'can_manage': True}, request=request)
                return HttpResponse(html, headers={'HX-Trigger': 'milestoneCreated'})
            return redirect('milestones:list', slug=slug)
        if request.headers.get('HX-Request'):
            from django.template.loader import render_to_string
            html = render_to_string('milestones/_form.jinja', {'form': form, 'project': project}, request=request)
            return HttpResponse(html, status=422)
        return redirect('milestones:list', slug=slug)


class MilestoneUpdateView(LoginRequiredMixin, View):
    def post(self, request, slug, pk):
        project = get_object_or_404(Project, slug=slug)
        ms = get_object_or_404(Milestone, pk=pk, project=project)
        if not user_can_manage_project(request.user, project):
            return HttpResponse(status=403)
        form = MilestoneForm(request.POST, instance=ms)
        if form.is_valid():
            form.save()
            if request.headers.get('HX-Request'):
                from django.template.loader import render_to_string
                html = render_to_string('milestones/_milestone_row.jinja', {'ms': ms, 'can_manage': True}, request=request)
                return HttpResponse(html)
            return redirect('milestones:list', slug=slug)
        return redirect('milestones:list', slug=slug)


class MilestoneDeleteView(LoginRequiredMixin, View):
    def post(self, request, slug, pk):
        project = get_object_or_404(Project, slug=slug)
        ms = get_object_or_404(Milestone, pk=pk, project=project)
        if not user_can_manage_project(request.user, project):
            return HttpResponse(status=403)
        ms.delete()
        if request.headers.get('HX-Request'):
            return HttpResponse('')
        return redirect('milestones:list', slug=slug)


class AllMilestonesView(LoginRequiredMixin, TemplateView):
    template_name = 'milestones/all.jinja'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        projects = get_user_projects(self.request.user)
        project_ids = projects.values_list('id', flat=True)
        ctx['milestones'] = Milestone.objects.filter(project_id__in=project_ids).select_related('project').order_by('due_date')
        return ctx
