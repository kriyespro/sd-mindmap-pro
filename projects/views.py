from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView

from projects.forms import ProjectForm
from projects.models import Project
from projects.services import (
    archive_project,
    clone_project,
    create_project,
    get_archived_projects,
    get_user_projects,
    unarchive_project,
    user_can_manage_project,
)


class ProjectListView(LoginRequiredMixin, TemplateView):
    template_name = 'projects/list.jinja'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['projects'] = get_user_projects(self.request.user)
        ctx['form'] = ProjectForm()
        return ctx


class ProjectCreateView(LoginRequiredMixin, View):
    def post(self, request):
        form = ProjectForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            team = data.pop('team', None)
            project = create_project(request.user, {**data, 'team': team})
            if request.headers.get('HX-Request'):
                projects = get_user_projects(request.user)
                from django.template.loader import render_to_string
                from django.template import RequestContext
                html = render_to_string(
                    'projects/_project_card.jinja',
                    {'project': project},
                    request=request,
                )
                return HttpResponse(html, headers={'HX-Trigger': 'projectCreated'})
            return redirect('projects:detail', slug=project.slug)
        if request.headers.get('HX-Request'):
            from django.template.loader import render_to_string
            html = render_to_string('projects/_create_form.jinja', {'form': form}, request=request)
            return HttpResponse(html, status=422)
        return redirect('projects:list')


class ProjectDetailView(LoginRequiredMixin, TemplateView):
    template_name = 'projects/detail.jinja'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        project = get_object_or_404(Project, slug=kwargs['slug'])
        ctx['project'] = project
        ctx['can_manage'] = user_can_manage_project(self.request.user, project)
        ctx['members'] = project.members.select_related('user').all()
        ctx['form'] = ProjectForm(instance=project)
        return ctx


class ProjectEditView(LoginRequiredMixin, View):
    def post(self, request, slug):
        project = get_object_or_404(Project, slug=slug)
        if not user_can_manage_project(request.user, project):
            return HttpResponse(status=403)
        form = ProjectForm(request.POST, instance=project)
        if form.is_valid():
            form.save()
            if request.headers.get('HX-Request'):
                return HttpResponse(
                    '<div class="text-green-400 text-sm py-2">Saved.</div>',
                    headers={'HX-Trigger': 'projectUpdated'},
                )
            return redirect('projects:detail', slug=project.slug)
        if request.headers.get('HX-Request'):
            from django.template.loader import render_to_string
            html = render_to_string('projects/_edit_form.jinja', {'form': form, 'project': project}, request=request)
            return HttpResponse(html, status=422)
        return redirect('projects:detail', slug=slug)


class ProjectArchiveView(LoginRequiredMixin, View):
    def post(self, request, slug):
        project = get_object_or_404(Project, slug=slug)
        if not user_can_manage_project(request.user, project):
            return HttpResponse(status=403)
        archive_project(project)
        if request.headers.get('HX-Request'):
            return HttpResponse('', headers={'HX-Redirect': '/projects/'})
        return redirect('projects:list')


class ProjectUnarchiveView(LoginRequiredMixin, View):
    def post(self, request, slug):
        project = get_object_or_404(Project, slug=slug)
        if not user_can_manage_project(request.user, project):
            return HttpResponse(status=403)
        unarchive_project(project)
        return redirect('projects:list')


class ProjectCloneView(LoginRequiredMixin, View):
    def post(self, request, slug):
        project = get_object_or_404(Project, slug=slug)
        clone = clone_project(project, request.user)
        return redirect('projects:detail', slug=clone.slug)


class ArchivedProjectListView(LoginRequiredMixin, TemplateView):
    template_name = 'projects/archived.jinja'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['projects'] = get_archived_projects(self.request.user)
        return ctx
