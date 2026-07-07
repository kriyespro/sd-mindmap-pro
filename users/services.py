from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction

User = get_user_model()

TUTORIAL_SLUG_PREFIX = 'welcome-tour-'


def tutorial_slug_for_user(user) -> str:
    return f'{TUTORIAL_SLUG_PREFIX}{user.pk}'


def is_tutorial_project(project) -> bool:
    return bool(project and project.slug.startswith(TUTORIAL_SLUG_PREFIX))


def get_tutorial_project(user):
    from projects.models import Project

    return Project.objects.filter(owner=user, slug=tutorial_slug_for_user(user)).first()


@transaction.atomic
def seed_tutorial_for_user(user) -> 'Project | None':
    """Create a one-time welcome tour project that demos core features."""
    from gantt.models import TaskDependency
    from milestones.models import Milestone
    from planner.models import Notification, Task, TaskChecklist, TaskComment
    from projects.models import Project, ProjectMember
    from users.models import Profile

    try:
        profile = user.profile
    except Profile.DoesNotExist:
        return None

    existing = get_tutorial_project(user)
    if profile.tutorial_seeded and existing:
        return existing

    today = date.today()
    slug = tutorial_slug_for_user(user)
    project, _ = Project.objects.get_or_create(
        slug=slug,
        defaults={
            'name': 'Welcome Tour',
            'owner': user,
            'status': Project.STATUS_ACTIVE,
            'priority': Project.PRIORITY_MEDIUM,
            'health': Project.HEALTH_ON_TRACK,
            'color': '#8b5cf6',
            'start_date': today - timedelta(days=3),
            'end_date': today + timedelta(days=14),
            'progress': 25,
            'description': (
                'Interactive demo project — explore Mindmap, Tree, Kanban, and Gantt. '
                'Each step is a task card you can click, complete, or edit.'
            ),
        },
    )
    ProjectMember.objects.get_or_create(
        project=project,
        user=user,
        defaults={'role': ProjectMember.ROLE_OWNER},
    )

    if Task.objects.filter(author=user, project=project).exists():
        profile.tutorial_seeded = True
        profile.save(update_fields=['tutorial_seeded'])
        return project

    def mk(parent, title, **kw):
        return Task.objects.create(
            author=user,
            project=project,
            parent=parent,
            team=None,
            title=title,
            **kw,
        )

    root = mk(
        None,
        'Start here — your product tour',
        start_date=today - timedelta(days=3),
        due_date=today + timedelta(days=14),
        status=Task.STATUS_IN_PROGRESS,
        priority=Task.PRIORITY_HIGH,
        description='Work through each step below. This project is yours — edit or delete anytime.',
        tags='tutorial,getting-started',
        position=0,
    )

    step1 = mk(
        root,
        '① Explore the Mindmap',
        start_date=today - timedelta(days=2),
        due_date=today + timedelta(days=2),
        status=Task.STATUS_IN_PROGRESS,
        priority=Task.PRIORITY_HIGH,
        description='Pan the canvas, zoom with scroll, and click any card to open task details.',
        position=1,
    )
    mk(
        step1,
        'Click a task card → details panel opens on the right',
        start_date=today - timedelta(days=1),
        due_date=today + timedelta(days=1),
        status=Task.STATUS_TODO,
        position=0,
    )
    mk(
        step1,
        'Use −/+ on cards to collapse or expand branches',
        start_date=today,
        due_date=today + timedelta(days=2),
        status=Task.STATUS_TODO,
        position=1,
    )

    step2 = mk(
        root,
        '② Switch board views (Tree · Map · Kanban)',
        start_date=today,
        due_date=today + timedelta(days=4),
        status=Task.STATUS_TODO,
        priority=Task.PRIORITY_MEDIUM,
        description='Use the tabs in the top bar to change how tasks are displayed.',
        position=2,
    )
    mk(
        step2,
        'Tree — nested list for execution focus',
        start_date=today,
        due_date=today + timedelta(days=3),
        status=Task.STATUS_TODO,
        position=0,
    )
    mk(
        step2,
        'Kanban — drag cards across status columns',
        start_date=today + timedelta(days=1),
        due_date=today + timedelta(days=5),
        status=Task.STATUS_TODO,
        position=1,
    )

    step3 = mk(
        root,
        '③ Open the Gantt chart',
        start_date=today + timedelta(days=2),
        due_date=today + timedelta(days=8),
        status=Task.STATUS_TODO,
        priority=Task.PRIORITY_MEDIUM,
        description='Tasks with start/due dates appear on the timeline. Try daily, weekly, or monthly zoom.',
        position=3,
    )
    gantt_child = mk(
        step3,
        'This task links to the next one (dependency arrow)',
        start_date=today + timedelta(days=5),
        due_date=today + timedelta(days=9),
        status=Task.STATUS_TODO,
        position=0,
    )

    step4 = mk(
        root,
        '④ Mark tasks complete',
        start_date=today + timedelta(days=1),
        due_date=today + timedelta(days=6),
        status=Task.STATUS_TODO,
        priority=Task.PRIORITY_LOW,
        description='Check the box on any card to mark it done. Progress updates on the project.',
        position=4,
    )
    demo_done = mk(
        step4,
        'Try checking this box ✓',
        start_date=today,
        due_date=today + timedelta(days=3),
        status=Task.STATUS_TODO,
        position=0,
    )

    TaskDependency.objects.get_or_create(
        predecessor=step3,
        successor=gantt_child,
        defaults={'dep_type': TaskDependency.TYPE_FS, 'lag_days': 0},
    )

    TaskChecklist.objects.bulk_create([
        TaskChecklist(task=demo_done, text='Open task details', position=0),
        TaskChecklist(task=demo_done, text='Add a checklist item', position=1),
        TaskChecklist(task=demo_done, text='Mark this task complete', position=2, is_done=False),
    ])
    TaskComment.objects.create(
        task=step1,
        author=user,
        body='Welcome! This sample comment shows team collaboration on tasks.',
    )

    Milestone.objects.get_or_create(
        project=project,
        name='Finish the welcome tour',
        defaults={
            'description': 'Complete all tour steps to feel confident using the app.',
            'due_date': today + timedelta(days=10),
            'status': Milestone.STATUS_IN_PROGRESS,
            'progress': 25,
            'created_by': user,
        },
    )

    if not Task.objects.filter(author=user, project__isnull=True, team__isnull=True).exists():
        personal = Task.objects.create(
            author=user,
            title='Personal workspace — your private goals',
            description='Tasks here are separate from projects. Great for personal OKRs and habits.',
            due_date=today + timedelta(days=7),
            status=Task.STATUS_TODO,
            priority=Task.PRIORITY_MEDIUM,
            tags='personal,tutorial',
        )
        Task.objects.create(
            author=user,
            parent=personal,
            title='Example: Ship a side project this month',
            due_date=today + timedelta(days=14),
            status=Task.STATUS_TODO,
            estimated_hours=Decimal('10'),
        )

    Notification.objects.create(
        user=user,
        message=(
            'Your Welcome Tour project is ready. Open it from Projects or follow the steps '
            'on the board to explore Mindmap, Kanban, and Gantt.'
        ),
    )

    profile.tutorial_seeded = True
    profile.save(update_fields=['tutorial_seeded'])
    return project
