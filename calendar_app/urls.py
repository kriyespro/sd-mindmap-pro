from django.urls import path
from calendar_app import views

app_name = 'calendar_app'

urlpatterns = [
    path('', views.CalendarView.as_view(), name='month'),
    path('partial/', views.CalendarMonthPartialView.as_view(), name='partial'),
]
