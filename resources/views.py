from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views import View

from resources.models import ResourceAllocation
from resources.services import get_workload_data, get_accessible_projects, get_project_allocations


class ResourceDashboardView(LoginRequiredMixin, View):
    def get(self, request):
        workload = get_workload_data(request.user, weeks=4)
        projects = get_accessible_projects(request.user)
        allocations = ResourceAllocation.objects.filter(
            project__owner=request.user
        ).select_related('user', 'project').order_by('project__name', 'user__username')
        return render(request, 'resources/dashboard.jinja', {
            'workload': workload,
            'projects': projects,
            'allocations': allocations,
            'today': date.today(),
        })


class ResourceAllocationCreateView(LoginRequiredMixin, View):
    def post(self, request):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user_id = request.POST.get('user_id', '').strip()
        project_id = request.POST.get('project_id', '').strip()
        role = request.POST.get('role', 'dev').strip()
        hours = request.POST.get('hours_per_day', '8').strip()
        start = request.POST.get('start_date', '').strip()
        end = request.POST.get('end_date', '').strip()
        notes = request.POST.get('notes', '').strip()

        if not all([user_id, start, end]):
            return HttpResponse('Missing required fields', status=400)

        try:
            user = User.objects.get(pk=user_id)
            from projects.models import Project
            project = Project.objects.get(pk=project_id) if project_id else None
            alloc = ResourceAllocation.objects.create(
                user=user,
                project=project,
                role=role,
                hours_per_day=float(hours),
                start_date=start,
                end_date=end,
                notes=notes,
                created_by=request.user,
            )
        except Exception:
            return HttpResponse('Invalid data', status=400)

        allocations = ResourceAllocation.objects.filter(
            project__owner=request.user
        ).select_related('user', 'project').order_by('project__name', 'user__username')
        return render(request, 'resources/_allocation_rows.jinja', {'allocations': allocations})


class ResourceAllocationDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        alloc = get_object_or_404(ResourceAllocation, pk=pk, created_by=request.user)
        alloc.delete()
        allocations = ResourceAllocation.objects.filter(
            project__owner=request.user
        ).select_related('user', 'project').order_by('project__name', 'user__username')
        return render(request, 'resources/_allocation_rows.jinja', {'allocations': allocations})
