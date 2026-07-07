from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from planner.models import Task
from projects.models import Project
from projects.services import create_project_task

User = get_user_model()


class ProjectBoardUnificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='boarduser', password='pass1234')
        self.client.force_login(self.user)
        self.project = Project.objects.create(
            name='Unified Project',
            owner=self.user,
            slug='unified-project',
        )

    def test_project_task_appears_on_board_and_gantt(self):
        create_project_task(
            self.user,
            self.project,
            {'title': 'Shared timeline task', 'status': Task.STATUS_TODO},
        )

        board_resp = self.client.get(
            reverse('projects:board', kwargs={'slug': self.project.slug})
        )
        self.assertEqual(board_resp.status_code, 200)
        self.assertContains(board_resp, 'Shared timeline task')

        gantt_resp = self.client.get(
            reverse('gantt:gantt', kwargs={'slug': self.project.slug})
        )
        self.assertEqual(gantt_resp.status_code, 200)
        self.assertContains(gantt_resp, 'Shared timeline task')

    def test_board_create_task_links_to_project(self):
        response = self.client.post(
            reverse('projects:board_task_create', kwargs={'slug': self.project.slug}),
            {'title': 'From mindmap board'},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 200)
        task = Task.objects.filter(project=self.project).first()
        self.assertIsNotNone(task)
        self.assertEqual(task.title_plain, 'From mindmap board')
