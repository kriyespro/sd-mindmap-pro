from django.urls import path
from timetracking import views

app_name = 'timetracking'

urlpatterns = [
    path('', views.TimeTrackingView.as_view(), name='index'),
    path('start/', views.TimerStartView.as_view(), name='start'),
    path('stop/', views.TimerStopView.as_view(), name='stop'),
    path('manual/', views.TimeEntryManualView.as_view(), name='manual'),
    path('entries/<int:pk>/delete/', views.TimeEntryDeleteView.as_view(), name='delete'),
]
