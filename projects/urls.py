from django.urls import path

from projects import views

app_name = 'projects'

urlpatterns = [
    path('', views.ProjectListView.as_view(), name='list'),
    path('archived/', views.ArchivedProjectListView.as_view(), name='archived'),
    path('create/', views.ProjectCreateView.as_view(), name='create'),
    path('<slug:slug>/', views.ProjectDetailView.as_view(), name='detail'),
    path('<slug:slug>/edit/', views.ProjectEditView.as_view(), name='edit'),
    path('<slug:slug>/archive/', views.ProjectArchiveView.as_view(), name='archive'),
    path('<slug:slug>/unarchive/', views.ProjectUnarchiveView.as_view(), name='unarchive'),
    path('<slug:slug>/clone/', views.ProjectCloneView.as_view(), name='clone'),
]
