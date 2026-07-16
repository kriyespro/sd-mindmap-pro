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


class Create99dTemplateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='bob', password='pass1234')
        self.client.force_login(self.user)

    def test_service_builds_1_3_9_tree(self):
        from planner.services import create_99d_template

        root = create_99d_template(author=self.user, root_title='')
        self.assertEqual(root.title_plain, '')
        mids = list(Task.objects.filter(parent=root).order_by('position', 'id'))
        self.assertEqual(len(mids), 3)
        self.assertTrue(all(m.title_plain == '' for m in mids))
        leaves = Task.objects.filter(parent__in=mids)
        self.assertEqual(leaves.count(), 9)
        self.assertTrue(all(t.title_plain == '' for t in leaves))
        self.assertEqual(Task.objects.count(), 13)

    def test_create_view_99d_template(self):
        response = self.client.post(
            reverse('planner:task_create_personal'),
            {'title': '', 'template': '99d', 'parent_id': ''},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Task.objects.count(), 13)
        root = Task.objects.get(parent__isnull=True)
        self.assertEqual(root.title_plain, '')
        self.assertEqual(Task.objects.filter(parent=root).count(), 3)
