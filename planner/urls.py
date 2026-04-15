from django.urls import path

from planner import views

app_name = 'planner'

urlpatterns = [
    path('app/', views.BoardView.as_view(), name='board_personal'),
    path('t/<slug:team_slug>/', views.BoardView.as_view(), name='board_team'),
    path('stats/', views.StatsPartialView.as_view(), name='stats_personal'),
    path('t/<slug:team_slug>/stats/', views.StatsPartialView.as_view(), name='stats_team'),
    path('tasks/', views.TaskCreateView.as_view(), name='task_create_personal'),
    path('t/<slug:team_slug>/tasks/', views.TaskCreateView.as_view(), name='task_create_team'),
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
]
