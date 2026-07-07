from django.urls import path
from milestones import views

app_name = 'milestones'

urlpatterns = [
    path('', views.AllMilestonesView.as_view(), name='all'),
    path('<slug:slug>/', views.MilestoneListView.as_view(), name='list'),
    path('<slug:slug>/create/', views.MilestoneCreateView.as_view(), name='create'),
    path('<slug:slug>/<int:pk>/update/', views.MilestoneUpdateView.as_view(), name='update'),
    path('<slug:slug>/<int:pk>/delete/', views.MilestoneDeleteView.as_view(), name='delete'),
]
