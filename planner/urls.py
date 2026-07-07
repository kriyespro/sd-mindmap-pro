from django.urls import path

from planner import views

app_name = 'planner'

urlpatterns = [
    path('app/', views.BoardView.as_view(), name='board_personal'),
    path('t/<slug:team_slug>/', views.BoardView.as_view(), name='board_team'),
    path('sidebar/my-tasks/', views.SidebarMyTasksPartialView.as_view(), name='sidebar_my_tasks'),
    path('stats/', views.StatsPartialView.as_view(), name='stats_personal'),
    path('t/<slug:team_slug>/stats/', views.StatsPartialView.as_view(), name='stats_team'),
    path('tasks/', views.TaskCreateView.as_view(), name='task_create_personal'),
    path('t/<slug:team_slug>/tasks/', views.TaskCreateView.as_view(), name='task_create_team'),
    path('tasks/partial/', views.TaskTreePartialView.as_view(), name='task_tree_partial_personal'),
    path(
        't/<slug:team_slug>/tasks/partial/',
        views.TaskTreePartialView.as_view(),
        name='task_tree_partial_team',
    ),
    path('tasks/import/', views.TaskImportView.as_view(), name='task_import_personal'),
    path('t/<slug:team_slug>/tasks/import/', views.TaskImportView.as_view(), name='task_import_team'),
    path('tasks/export/', views.TaskExportCsvView.as_view(), name='task_export_personal'),
    path('t/<slug:team_slug>/tasks/export/', views.TaskExportCsvView.as_view(), name='task_export_team'),
    path('tasks/export-mindmap/', views.MindmapExportView.as_view(), name='mindmap_export_personal'),
    path(
        't/<slug:team_slug>/tasks/export-mindmap/',
        views.MindmapExportView.as_view(),
        name='mindmap_export_team',
    ),
    path('tasks/<int:task_id>/status/', views.TaskToggleView.as_view(), name='task_toggle_personal'),
    path(
        't/<slug:team_slug>/tasks/<int:task_id>/status/',
        views.TaskToggleView.as_view(),
        name='task_toggle_team',
    ),
    path('tasks/<int:task_id>/delete/', views.TaskDeleteView.as_view(), name='task_delete_personal'),
    path(
        't/<slug:team_slug>/tasks/<int:task_id>/delete/',
        views.TaskDeleteView.as_view(),
        name='task_delete_team',
    ),
    path('tasks/<int:task_id>/title/', views.TaskRenameView.as_view(), name='task_title_personal'),
    path(
        't/<slug:team_slug>/tasks/<int:task_id>/title/',
        views.TaskRenameView.as_view(),
        name='task_title_team',
    ),
    path('tasks/<int:task_id>/meta/', views.TaskMetaView.as_view(), name='task_meta_personal'),
    path(
        't/<slug:team_slug>/tasks/<int:task_id>/meta/',
        views.TaskMetaView.as_view(),
        name='task_meta_team',
    ),
    path('notifications/<int:n_id>/read/', views.NotificationReadView.as_view(), name='notification_read'),
    path(
        'tasks/<int:task_id>/mindmap-collapse/',
        views.MindmapCollapseToggleView.as_view(),
        name='mindmap_collapse_personal',
    ),
    path(
        't/<slug:team_slug>/tasks/<int:task_id>/mindmap-collapse/',
        views.MindmapCollapseToggleView.as_view(),
        name='mindmap_collapse_team',
    ),
    path(
        'tasks/mindmap-collapse-all/',
        views.MindmapCollapseAllView.as_view(),
        name='mindmap_collapse_all_personal',
    ),
    path(
        't/<slug:team_slug>/tasks/mindmap-collapse-all/',
        views.MindmapCollapseAllView.as_view(),
        name='mindmap_collapse_all_team',
    ),
    path(
        'tasks/mindmap-expand-all/',
        views.MindmapExpandAllView.as_view(),
        name='mindmap_expand_all_personal',
    ),
    path(
        't/<slug:team_slug>/tasks/mindmap-expand-all/',
        views.MindmapExpandAllView.as_view(),
        name='mindmap_expand_all_team',
    ),
    path(
        't/<slug:team_slug>/tasks/archive-mindmap/',
        views.TeamMindmapArchiveView.as_view(),
        name='archive_team_mindmap',
    ),
    path(
        't/<slug:team_slug>/tasks/unarchive-mindmap/',
        views.TeamMindmapUnarchiveView.as_view(),
        name='unarchive_team_mindmap',
    ),
    path(
        'tasks/<int:task_id>/kanban-status/',
        views.TaskKanbanStatusView.as_view(),
        name='kanban_status_personal',
    ),
    path(
        't/<slug:team_slug>/tasks/<int:task_id>/kanban-status/',
        views.TaskKanbanStatusView.as_view(),
        name='kanban_status_team',
    ),
    # Task detail panel
    path('tasks/<int:task_id>/detail/', views.TaskDetailModalView.as_view(), name='task_detail'),
    path('tasks/<int:task_id>/comments/', views.TaskCommentCreateView.as_view(), name='task_comment_create'),
    path('tasks/<int:task_id>/comments/<int:comment_id>/delete/', views.TaskCommentDeleteView.as_view(), name='task_comment_delete'),
    path('tasks/<int:task_id>/checklist/', views.TaskChecklistCreateView.as_view(), name='task_checklist_create'),
    path('tasks/<int:task_id>/checklist/<int:item_id>/toggle/', views.TaskChecklistToggleView.as_view(), name='task_checklist_toggle'),
    path('tasks/<int:task_id>/checklist/<int:item_id>/delete/', views.TaskChecklistDeleteView.as_view(), name='task_checklist_delete'),
]
