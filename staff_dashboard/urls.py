from django.urls import path

from staff_dashboard import views

app_name = 'staff_dashboard'

urlpatterns = [
    path('', views.StaffDashboardView.as_view(), name='dashboard'),
]
