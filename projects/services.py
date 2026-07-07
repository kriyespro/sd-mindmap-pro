from django.contrib.auth import get_user_model
from django.db.models import QuerySet

from planner.models import Task
from projects.models import Project, ProjectMember

User = get_user_model()


def get_user_projects(user) -> QuerySet:
    owned = Project.objects.filter(owner=user, is_archived=False)
    member_ids = ProjectMember.objects.filter(user=user).values_list('project_id', flat=True)
    member_projects = Project.objects.filter(id__in=member_ids, is_archived=False)
    return (owned | member_projects).distinct().select_related('owner', 'manager', 'team')


def get_archived_projects(user) -> QuerySet:
    owned = Project.objects.filter(owner=user, is_archived=True)
    member_ids = ProjectMember.objects.filter(user=user).values_list('project_id', flat=True)
    member_projects = Project.objects.filter(id__in=member_ids, is_archived=True)
    return (owned | member_projects).distinct().select_related('owner', 'manager', 'team')


def create_project(user, form_data: dict) -> Project:
    project = Project(**form_data, owner=user)
    project.save()
    ProjectMember.objects.create(project=project, user=user, role=ProjectMember.ROLE_OWNER)
    return project


def archive_project(project: Project) -> None:
    project.is_archived = True
    project.save(update_fields=['is_archived'])


def unarchive_project(project: Project) -> None:
    project.is_archived = False
    project.save(update_fields=['is_archived'])


def clone_project(project: Project, user) -> Project:
    clone = Project(
        name=f'Copy of {project.name}',
        description=project.description,
        status=Project.STATUS_PLANNING,
        priority=project.priority,
        health=Project.HEALTH_ON_TRACK,
        owner=user,
        team=project.team,
        client_name=project.client_name,
        budget=project.budget,
        start_date=project.start_date,
        end_date=project.end_date,
        color=project.color,
    )
    clone.save()
    ProjectMember.objects.create(project=clone, user=user, role=ProjectMember.ROLE_OWNER)
    return clone


def user_can_manage_project(user, project: Project) -> bool:
    if project.owner == user:
        return True
    return ProjectMember.objects.filter(
        project=project, user=user, role__in=[ProjectMember.ROLE_OWNER, ProjectMember.ROLE_MANAGER]
    ).exists()


def user_can_access_project(user, project: Project) -> bool:
    if project.owner_id == user.id:
        return True
    return ProjectMember.objects.filter(project=project, user=user).exists()


def get_project_tasks(project: Project) -> QuerySet[Task]:
    return (
        Task.objects.filter(project=project, is_archived=False)
        .select_related('project')
        .order_by('position', 'id')
    )


def create_project_task(user, project: Project, data: dict) -> Task:
    task = Task(
        author=user,
        project=project,
        team=project.team,
        **data,
    )
    task.save()
    update_project_progress(project)
    return task


def user_can_edit_project_task(user, task: Task) -> bool:
    if task.project_id is None:
        return False
    return user_can_access_project(user, task.project)


def update_project_progress(project: Project) -> None:
    from planner.models import Task
    tasks = Task.objects.filter(project=project)
    total = tasks.count()
    if total == 0:
        project.progress = 0
    else:
        done = tasks.filter(is_completed=True).count()
        project.progress = int(done / total * 100)
    project.save(update_fields=['progress'])
