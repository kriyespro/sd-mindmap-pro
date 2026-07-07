"""
Seed demo user with rich data across all features:
  Projects, Tasks (with dates/priority/status/tags/checklist/comments),
  Milestones, TimeEntries, ResourceAllocations, TaskDependencies, Gantt data.
"""

from datetime import date, timedelta, datetime, timezone as dt_tz
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

User = get_user_model()


class Command(BaseCommand):
    help = 'Seed demo/demo1234 with full PM data (projects, tasks, gantt, milestones, time, resources).'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Wipe all demo data before re-seeding.')

    @transaction.atomic
    def handle(self, *args, **options):
        # ── Users ──────────────────────────────────────────────────────────────
        demo, _ = User.objects.get_or_create(username='demo', defaults={'email': 'demo@example.com', 'first_name': 'Demo', 'last_name': 'User'})
        demo.set_password('demo1234')
        demo.save()

        alice, _ = User.objects.get_or_create(username='alice', defaults={'email': 'alice@example.com', 'first_name': 'Alice'})
        alice.set_password('demo1234')
        alice.save()

        bob, _ = User.objects.get_or_create(username='bob', defaults={'email': 'bob@example.com', 'first_name': 'Bob'})
        bob.set_password('demo1234')
        bob.save()

        self.stdout.write(self.style.SUCCESS('Users: demo / alice / bob (all password: demo1234)'))

        # ── Reset ──────────────────────────────────────────────────────────────
        if options['reset']:
            from planner.models import Task
            from projects.models import Project
            from milestones.models import Milestone
            from timetracking.models import TimeEntry
            from resources.models import ResourceAllocation
            Task.objects.filter(author=demo).delete()
            Project.objects.filter(owner=demo).delete()
            Milestone.objects.filter(created_by=demo).delete()
            TimeEntry.objects.filter(user=demo).delete()
            ResourceAllocation.objects.filter(created_by=demo).delete()
            self.stdout.write(self.style.WARNING('Demo data wiped.'))

        today = date.today()

        # ── Import models ──────────────────────────────────────────────────────
        from planner.models import Task, TaskComment, TaskChecklist
        from projects.models import Project, ProjectMember
        from milestones.models import Milestone, MilestoneTask
        from timetracking.models import TimeEntry
        from resources.models import ResourceAllocation
        from gantt.models import TaskDependency

        # ── Projects ───────────────────────────────────────────────────────────
        def get_or_create_project(name, slug, **kwargs):
            p, created = Project.objects.get_or_create(
                slug=slug,
                defaults={'name': name, 'owner': demo, **kwargs}
            )
            return p

        p1 = get_or_create_project(
            'Website Redesign', 'website-redesign',
            status='active', priority='high', health='on_track',
            color='#6366f1', start_date=today - timedelta(days=14),
            end_date=today + timedelta(days=30), progress=45,
            client_name='Acme Corp', budget=Decimal('15000.00'),
            description='Complete redesign of the corporate website with new brand identity.',
        )
        p2 = get_or_create_project(
            'Mobile App v2', 'mobile-app-v2',
            status='active', priority='critical', health='at_risk',
            color='#f97316', start_date=today - timedelta(days=7),
            end_date=today + timedelta(days=60), progress=20,
            client_name='Internal', budget=Decimal('40000.00'),
            description='Rebuild the iOS/Android app with React Native.',
        )
        p3 = get_or_create_project(
            'API Integration', 'api-integration',
            status='planning', priority='medium', health='on_track',
            color='#22c55e', start_date=today + timedelta(days=5),
            end_date=today + timedelta(days=45), progress=0,
            description='Integrate third-party payment and analytics APIs.',
        )
        p4 = get_or_create_project(
            'Brand Identity', 'brand-identity',
            status='completed', priority='low', health='on_track',
            color='#a855f7', start_date=today - timedelta(days=60),
            end_date=today - timedelta(days=5), progress=100,
            description='Logo, color palette, typography system.',
        )

        # Add members
        for p in [p1, p2, p3]:
            ProjectMember.objects.get_or_create(project=p, user=alice, defaults={'role': 'member'})
            ProjectMember.objects.get_or_create(project=p, user=bob, defaults={'role': 'member'})

        self.stdout.write(self.style.SUCCESS('Projects created: 4'))

        # ── Tasks helper ───────────────────────────────────────────────────────
        def mk(parent, title, project=None, **kw):
            t, _ = Task.objects.get_or_create(
                author=demo, title=title, parent=parent,
                defaults={'team': None, 'project': project, **kw}
            )
            return t

        # ── P1: Website Redesign tasks (with Gantt dates) ──────────────────────
        if not Task.objects.filter(author=demo, project=p1).exists():
            t_disc = mk(None, 'Discovery & Research', project=p1,
                start_date=today - timedelta(days=14), due_date=today - timedelta(days=7),
                status='done', priority='high', is_completed=True,
                description='Stakeholder interviews, competitor analysis, user research.',
                tags='research,discovery', estimated_hours=Decimal('20'))
            mk(t_disc, 'Stakeholder interviews', project=p1,
                start_date=today - timedelta(days=14), due_date=today - timedelta(days=10),
                status='done', is_completed=True, priority='high', estimated_hours=Decimal('8'))
            mk(t_disc, 'Competitor analysis', project=p1,
                start_date=today - timedelta(days=12), due_date=today - timedelta(days=8),
                status='done', is_completed=True, priority='medium', estimated_hours=Decimal('6'))
            mk(t_disc, 'User survey', project=p1,
                start_date=today - timedelta(days=10), due_date=today - timedelta(days=7),
                status='done', is_completed=True, priority='medium', estimated_hours=Decimal('6'))

            t_design = mk(None, 'Design System', project=p1,
                start_date=today - timedelta(days=7), due_date=today + timedelta(days=7),
                status='in_progress', priority='critical',
                description='Build comprehensive design system: colors, typography, components.',
                tags='design,ui', estimated_hours=Decimal('40'))
            t_wf = mk(t_design, 'Wireframes', project=p1,
                start_date=today - timedelta(days=7), due_date=today - timedelta(days=2),
                status='done', is_completed=True, priority='high', estimated_hours=Decimal('16'))
            t_proto = mk(t_design, 'High-fidelity prototypes', project=p1,
                start_date=today - timedelta(days=2), due_date=today + timedelta(days=5),
                status='in_progress', priority='critical', estimated_hours=Decimal('20'),
                assignee_username='alice')
            mk(t_design, 'Component library', project=p1,
                start_date=today + timedelta(days=3), due_date=today + timedelta(days=7),
                status='todo', priority='high', estimated_hours=Decimal('12'),
                assignee_username='bob')

            t_dev = mk(None, 'Frontend Development', project=p1,
                start_date=today + timedelta(days=7), due_date=today + timedelta(days=25),
                status='todo', priority='high',
                description='Implement designs in Next.js with Tailwind CSS.',
                tags='frontend,nextjs', estimated_hours=Decimal('80'))
            mk(t_dev, 'Setup Next.js project', project=p1,
                start_date=today + timedelta(days=7), due_date=today + timedelta(days=9),
                status='todo', priority='high', estimated_hours=Decimal('8'))
            mk(t_dev, 'Header & navigation', project=p1,
                start_date=today + timedelta(days=9), due_date=today + timedelta(days=13),
                status='todo', priority='medium', estimated_hours=Decimal('12'), assignee_username='alice')
            mk(t_dev, 'Landing page', project=p1,
                start_date=today + timedelta(days=11), due_date=today + timedelta(days=18),
                status='todo', priority='high', estimated_hours=Decimal('20'), assignee_username='bob')
            mk(t_dev, 'Blog & CMS integration', project=p1,
                start_date=today + timedelta(days=15), due_date=today + timedelta(days=22),
                status='todo', priority='medium', estimated_hours=Decimal('24'))
            mk(t_dev, 'Contact & forms', project=p1,
                start_date=today + timedelta(days=20), due_date=today + timedelta(days=25),
                status='todo', priority='low', estimated_hours=Decimal('8'))

            t_qa = mk(None, 'QA & Launch', project=p1,
                start_date=today + timedelta(days=25), due_date=today + timedelta(days=30),
                status='todo', priority='critical',
                description='Full QA pass, performance audit, launch.',
                tags='qa,launch', estimated_hours=Decimal('24'))
            mk(t_qa, 'Cross-browser testing', project=p1,
                start_date=today + timedelta(days=25), due_date=today + timedelta(days=27),
                status='todo', priority='high', estimated_hours=Decimal('8'))
            mk(t_qa, 'Performance optimization', project=p1,
                start_date=today + timedelta(days=27), due_date=today + timedelta(days=29),
                status='todo', priority='high', estimated_hours=Decimal('8'))
            mk(t_qa, 'Go live', project=p1,
                start_date=today + timedelta(days=29), due_date=today + timedelta(days=30),
                status='todo', priority='critical', estimated_hours=Decimal('4'))

            # Gantt dependencies
            if t_wf and t_proto:
                TaskDependency.objects.get_or_create(predecessor=t_wf, successor=t_proto, defaults={'dep_type': 'FS'})
            if t_proto and t_dev:
                TaskDependency.objects.get_or_create(predecessor=t_proto, successor=t_dev, defaults={'dep_type': 'FS'})
            if t_dev and t_qa:
                TaskDependency.objects.get_or_create(predecessor=t_dev, successor=t_qa, defaults={'dep_type': 'FS'})

        # ── P2: Mobile App v2 tasks ────────────────────────────────────────────
        if not Task.objects.filter(author=demo, project=p2).exists():
            t_arch = mk(None, 'Architecture', project=p2,
                start_date=today - timedelta(days=7), due_date=today,
                status='in_progress', priority='critical',
                description='React Native architecture, state management, navigation.',
                tags='architecture,rn', estimated_hours=Decimal('16'))
            mk(t_arch, 'Tech stack decision', project=p2,
                start_date=today - timedelta(days=7), due_date=today - timedelta(days=5),
                status='done', is_completed=True, priority='critical', estimated_hours=Decimal('4'))
            mk(t_arch, 'Repo & CI setup', project=p2,
                start_date=today - timedelta(days=5), due_date=today - timedelta(days=2),
                status='in_progress', priority='high', estimated_hours=Decimal('8'), assignee_username='bob')
            mk(t_arch, 'API design', project=p2,
                start_date=today - timedelta(days=3), due_date=today + timedelta(days=2),
                status='in_progress', priority='high', estimated_hours=Decimal('12'), assignee_username='alice')

            t_auth = mk(None, 'Authentication', project=p2,
                start_date=today + timedelta(days=1), due_date=today + timedelta(days=10),
                status='todo', priority='critical',
                description='Login, registration, biometric auth, OAuth.',
                tags='auth,security', estimated_hours=Decimal('32'))
            mk(t_auth, 'Login screen', project=p2,
                start_date=today + timedelta(days=1), due_date=today + timedelta(days=4),
                status='todo', priority='high', estimated_hours=Decimal('8'), assignee_username='alice')
            mk(t_auth, 'Biometric (Face ID / Touch ID)', project=p2,
                start_date=today + timedelta(days=4), due_date=today + timedelta(days=8),
                status='todo', priority='medium', estimated_hours=Decimal('16'))
            mk(t_auth, 'Google OAuth', project=p2,
                start_date=today + timedelta(days=6), due_date=today + timedelta(days=10),
                status='todo', priority='medium', estimated_hours=Decimal('8'))

            t_core = mk(None, 'Core Features', project=p2,
                start_date=today + timedelta(days=10), due_date=today + timedelta(days=40),
                status='todo', priority='high',
                description='Dashboard, task list, push notifications.',
                tags='features,core', estimated_hours=Decimal('80'))
            mk(t_core, 'Dashboard screen', project=p2,
                start_date=today + timedelta(days=10), due_date=today + timedelta(days=18),
                status='todo', priority='high', estimated_hours=Decimal('20'), assignee_username='alice')
            mk(t_core, 'Task list & detail', project=p2,
                start_date=today + timedelta(days=15), due_date=today + timedelta(days=28),
                status='todo', priority='high', estimated_hours=Decimal('32'), assignee_username='bob')
            mk(t_core, 'Push notifications', project=p2,
                start_date=today + timedelta(days=25), due_date=today + timedelta(days=35),
                status='todo', priority='medium', estimated_hours=Decimal('16'))
            mk(t_core, 'Offline mode', project=p2,
                start_date=today + timedelta(days=30), due_date=today + timedelta(days=40),
                status='todo', priority='low', estimated_hours=Decimal('24'))

        # ── P3: API Integration tasks ──────────────────────────────────────────
        if not Task.objects.filter(author=demo, project=p3).exists():
            mk(None, 'Stripe payment integration', project=p3,
                start_date=today + timedelta(days=5), due_date=today + timedelta(days=15),
                status='todo', priority='critical',
                description='Implement Stripe checkout, webhooks, subscription billing.',
                tags='payments,stripe', estimated_hours=Decimal('24'))
            mk(None, 'Google Analytics 4 setup', project=p3,
                start_date=today + timedelta(days=5), due_date=today + timedelta(days=10),
                status='todo', priority='medium', tags='analytics',
                estimated_hours=Decimal('8'))
            mk(None, 'SendGrid email integration', project=p3,
                start_date=today + timedelta(days=10), due_date=today + timedelta(days=18),
                status='todo', priority='high', tags='email',
                estimated_hours=Decimal('12'))
            mk(None, 'Sentry error tracking', project=p3,
                start_date=today + timedelta(days=15), due_date=today + timedelta(days=20),
                status='todo', priority='medium', tags='monitoring',
                estimated_hours=Decimal('6'))

        # ── Personal tasks (no project) ────────────────────────────────────────
        if not Task.objects.filter(author=demo, project__isnull=True, team__isnull=True).exists():
            root = mk(None, 'Personal OKRs')
            q = mk(root, 'Q3 Goals', due_date=today + timedelta(days=45))
            mk(q, 'Ship 2 projects', due_date=today + timedelta(days=30), status='in_progress', priority='high')
            mk(q, 'Learn Rust basics', due_date=today + timedelta(days=45), status='todo', priority='low')
            mk(q, 'Run 5K', due_date=today + timedelta(days=20), status='todo', priority='medium')
            admin = mk(root, 'Admin')
            mk(admin, 'Renew SSL cert', due_date=today + timedelta(days=3), priority='critical')
            mk(admin, 'Update dependencies', due_date=today + timedelta(days=7), priority='high')
            mk(admin, 'Backup database', due_date=today - timedelta(days=1), priority='high', is_completed=True, status='done')

        # ── Checklist + Comments on high-priority tasks ────────────────────────
        for task in Task.objects.filter(author=demo, project=p1, status='in_progress')[:2]:
            if not task.checklist_items.exists():
                items = [
                    ('Review design specs', True),
                    ('Set up dev environment', True),
                    ('Implement base layout', False),
                    ('Add responsive breakpoints', False),
                    ('Write unit tests', False),
                ]
                for i, (text, done) in enumerate(items):
                    TaskChecklist.objects.create(task=task, text=text, is_done=done, position=i)

            if not task.comments.exists():
                TaskComment.objects.create(task=task, author=demo, body='Starting on this today. Design specs look good, just need to align on mobile breakpoints.')
                TaskComment.objects.create(task=task, author=alice, body='@demo the Figma file has been updated with the latest changes. Check the v3 frame.')
                TaskComment.objects.create(task=task, author=bob, body='I can help with the responsive implementation once the base layout is done.')

        for task in Task.objects.filter(author=demo, project=p2, status__in=['in_progress', 'todo'])[:2]:
            if not task.checklist_items.exists():
                items = [
                    ('Read API documentation', True),
                    ('Set up test environment', True),
                    ('Implement core logic', False),
                    ('Add error handling', False),
                    ('Write tests', False),
                    ('Code review', False),
                ]
                for i, (text, done) in enumerate(items):
                    TaskChecklist.objects.create(task=task, text=text, is_done=done, position=i)

            if not task.comments.exists():
                TaskComment.objects.create(task=task, author=alice, body='This is blocked by the API design task. Once that is done we can move fast.')
                TaskComment.objects.create(task=task, author=demo, body='Agreed. I am targeting EOD Friday for the API design, then we can kick this off Monday.')

        self.stdout.write(self.style.SUCCESS('Tasks + Checklist + Comments seeded'))

        # ── Milestones ─────────────────────────────────────────────────────────
        def mk_ms(project, name, due_offset, status='pending', progress=0):
            ms, _ = Milestone.objects.get_or_create(
                project=project, name=name,
                defaults={
                    'due_date': today + timedelta(days=due_offset),
                    'status': status, 'progress': progress,
                    'created_by': demo,
                }
            )
            return ms

        mk_ms(p1, 'Design Approved', -2, status='completed', progress=100)
        mk_ms(p1, 'Frontend Complete', 25, status='in_progress', progress=30)
        mk_ms(p1, 'Website Launch', 30, status='pending', progress=0)
        mk_ms(p2, 'Architecture Sign-off', 0, status='in_progress', progress=70)
        mk_ms(p2, 'Alpha Build', 20, status='pending', progress=0)
        mk_ms(p2, 'Beta Release', 45, status='pending', progress=0)
        mk_ms(p3, 'API Contracts Finalized', 8, status='pending', progress=0)
        mk_ms(p3, 'Integration Complete', 40, status='pending', progress=0)

        self.stdout.write(self.style.SUCCESS('Milestones seeded'))

        # ── Time Entries ───────────────────────────────────────────────────────
        def mk_time(user, project, task_title, hours, days_ago, description=''):
            task = Task.objects.filter(author=demo, project=project, title__icontains=task_title).first()
            started = timezone.now() - timedelta(days=days_ago, hours=2)
            stopped = started + timedelta(hours=hours)
            TimeEntry.objects.get_or_create(
                user=user, project=project, task=task,
                started_at=started,
                defaults={
                    'stopped_at': stopped,
                    'duration_seconds': int(hours * 3600),
                    'status': 'stopped',
                    'description': description or f'Work on {task_title}',
                }
            )

        # Demo user logged time this week and last week
        for i, (proj, title, hours, days_ago) in enumerate([
            (p1, 'High-fidelity', 3.5, 0),
            (p1, 'Wireframes', 4.0, 1),
            (p1, 'Stakeholder', 2.0, 2),
            (p2, 'API design', 3.0, 0),
            (p2, 'Repo', 2.5, 3),
            (p1, 'High-fidelity', 4.0, 7),
            (p1, 'Component', 3.0, 8),
            (p2, 'Tech stack', 1.5, 9),
            (p1, 'Discovery', 5.0, 10),
            (p2, 'Architecture', 4.0, 12),
        ]):
            mk_time(demo, proj, title, hours, days_ago)

        # Alice and Bob also logged some time
        for (proj, title, hours, days_ago) in [
            (p1, 'High-fidelity', 5.0, 0),
            (p1, 'Wireframes', 3.0, 2),
            (p2, 'API design', 4.0, 1),
        ]:
            mk_time(alice, proj, title, hours, days_ago)

        for (proj, title, hours, days_ago) in [
            (p2, 'Repo', 6.0, 1),
            (p1, 'Component', 4.0, 3),
        ]:
            mk_time(bob, proj, title, hours, days_ago)

        self.stdout.write(self.style.SUCCESS('Time entries seeded'))

        # ── Resource Allocations ───────────────────────────────────────────────
        def mk_alloc(user, project, role, h_per_day, start_offset, end_offset):
            ResourceAllocation.objects.get_or_create(
                user=user, project=project,
                start_date=today + timedelta(days=start_offset),
                end_date=today + timedelta(days=end_offset),
                defaults={
                    'role': role, 'hours_per_day': Decimal(str(h_per_day)),
                    'created_by': demo,
                }
            )

        mk_alloc(demo, p1, 'pm', 6, -14, 30)
        mk_alloc(alice, p1, 'design', 8, -7, 7)
        mk_alloc(bob, p1, 'dev', 8, 7, 30)
        mk_alloc(demo, p2, 'pm', 4, -7, 60)
        mk_alloc(alice, p2, 'dev', 8, -7, 40)
        mk_alloc(bob, p2, 'dev', 8, -5, 40)
        mk_alloc(demo, p3, 'pm', 2, 5, 45)
        mk_alloc(alice, p3, 'dev', 6, 5, 35)

        self.stdout.write(self.style.SUCCESS('Resource allocations seeded'))

        # ── Summary ────────────────────────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 55))
        self.stdout.write(self.style.SUCCESS('SEED COMPLETE'))
        self.stdout.write(self.style.SUCCESS('=' * 55))
        self.stdout.write(f'  Projects:      {4}')
        self.stdout.write(f'  Tasks:         {Task.objects.filter(author=demo).count()}')
        self.stdout.write(f'  Milestones:    {8}')
        self.stdout.write(f'  Time entries:  {TimeEntry.objects.count()}')
        self.stdout.write(f'  Allocations:   {ResourceAllocation.objects.count()}')
        self.stdout.write('')
        self.stdout.write('  Login:   demo / demo1234')
        self.stdout.write('  Also:    alice / demo1234 | bob / demo1234')
        self.stdout.write('')
        self.stdout.write('  Gantt:   /gantt/website-redesign/')
        self.stdout.write('  Gantt:   /gantt/mobile-app-v2/')
        self.stdout.write('  Board:   /app/')
        self.stdout.write('  Reports: /reports/')
        self.stdout.write('  Resources: /resources/')
        self.stdout.write(self.style.SUCCESS('=' * 55))
