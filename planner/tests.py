from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from planner.models import Task

User = get_user_model()


class TaskImportViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='alice', password='pass1234')
        self.client.force_login(self.user)

    def test_import_csv_task_subtask_columns(self):
        payload = b"task,subtask\nWebsite Redesign,Create wireframes\nWebsite Redesign,Get approvals\n"
        upload = SimpleUploadedFile('tasks.csv', payload, content_type='text/csv')

        response = self.client.post(
            reverse('planner:task_import_personal'),
            {'file': upload},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 200)
        root = next(t for t in Task.objects.all() if t.title_plain == 'Website Redesign')
        self.assertIsNone(root.parent_id)
        self.assertEqual(Task.objects.filter(parent=root).count(), 2)

    def test_import_txt_with_indentation_creates_subtasks(self):
        payload = b"Launch Plan\n  Landing page\n  Email campaign\n"
        upload = SimpleUploadedFile('tasks.txt', payload, content_type='text/plain')

        response = self.client.post(
            reverse('planner:task_import_personal'),
            {'file': upload},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 200)
        root = next(t for t in Task.objects.all() if t.title_plain == 'Launch Plan')
        subtasks = Task.objects.filter(parent=root).order_by('id')
        self.assertEqual(subtasks.count(), 2)
        self.assertEqual(subtasks[0].title_plain, 'Landing page')
        self.assertEqual(subtasks[1].title_plain, 'Email campaign')
