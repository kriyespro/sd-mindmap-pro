from django.urls import path

from gantt import views

app_name = 'gantt'

urlpatterns = [
    path('', views.GanttProjectListView.as_view(), name='project_list'),
    path('<slug:slug>/', views.GanttView.as_view(), name='gantt'),
    path('<slug:slug>/partial/', views.GanttPartialView.as_view(), name='partial'),
    path('tasks/<int:task_id>/dates/', views.TaskDateUpdateView.as_view(), name='task_dates'),
]
