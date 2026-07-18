from django.urls import path

from planner import views as planner_views
from projects import views

app_name = 'projects'

urlpatterns = [
    path('', views.ProjectListView.as_view(), name='list'),
    path('archived/', views.ArchivedProjectListView.as_view(), name='archived'),
    path('create/', views.ProjectCreateView.as_view(), name='create'),
    path('<slug:slug>/tasks/create/', views.ProjectTaskCreateView.as_view(), name='task_create'),
    # Project board — same tasks as Gantt (mindmap / tree / kanban)
    path('<slug:slug>/board/', planner_views.BoardView.as_view(), name='board'),
    path('<slug:slug>/board/stats/', planner_views.StatsPartialView.as_view(), name='board_stats'),
    path('<slug:slug>/board/tasks/', planner_views.TaskCreateView.as_view(), name='board_task_create'),
    path(
        '<slug:slug>/board/tasks/partial/',
        planner_views.TaskTreePartialView.as_view(),
        name='board_task_tree_partial',
    ),
    path(
        '<slug:slug>/board/tasks/<int:task_id>/status/',
        planner_views.TaskToggleView.as_view(),
        name='board_task_toggle',
    ),
    path(
        '<slug:slug>/board/tasks/<int:task_id>/delete/',
        planner_views.TaskDeleteView.as_view(),
        name='board_task_delete',
    ),
    path(
        '<slug:slug>/board/tasks/<int:task_id>/title/',
        planner_views.TaskRenameView.as_view(),
        name='board_task_title',
    ),
    path(
        '<slug:slug>/board/tasks/<int:task_id>/meta/',
        planner_views.TaskMetaView.as_view(),
        name='board_task_meta',
    ),
    path(
        '<slug:slug>/board/tasks/<int:task_id>/mindmap-collapse/',
        planner_views.MindmapCollapseToggleView.as_view(),
        name='board_mindmap_collapse',
    ),
    path(
        '<slug:slug>/board/tasks/mindmap-collapse-all/',
        planner_views.MindmapCollapseAllView.as_view(),
        name='board_mindmap_collapse_all',
    ),
    path(
        '<slug:slug>/board/tasks/mindmap-expand-all/',
        planner_views.MindmapExpandAllView.as_view(),
        name='board_mindmap_expand_all',
    ),
    path(
        '<slug:slug>/board/tasks/mindmap-focus/',
        planner_views.MindmapFocusDepthView.as_view(),
        name='board_mindmap_focus',
    ),
    path(
        '<slug:slug>/board/tasks/<int:task_id>/kanban-status/',
        planner_views.TaskKanbanStatusView.as_view(),
        name='board_kanban_status',
    ),
    path('<slug:slug>/members/add/', views.ProjectMemberAddView.as_view(), name='member_add'),
    path('<slug:slug>/', views.ProjectDetailView.as_view(), name='detail'),
    path('<slug:slug>/edit/', views.ProjectEditView.as_view(), name='edit'),
    path('<slug:slug>/archive/', views.ProjectArchiveView.as_view(), name='archive'),
    path('<slug:slug>/unarchive/', views.ProjectUnarchiveView.as_view(), name='unarchive'),
    path('<slug:slug>/clone/', views.ProjectCloneView.as_view(), name='clone'),
]
