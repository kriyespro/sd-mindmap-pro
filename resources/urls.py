from django.urls import path
from resources import views

app_name = 'resources'

urlpatterns = [
    path('', views.ResourceDashboardView.as_view(), name='dashboard'),
    path('allocations/', views.ResourceAllocationCreateView.as_view(), name='allocation_create'),
    path('allocations/<int:pk>/delete/', views.ResourceAllocationDeleteView.as_view(), name='allocation_delete'),
]
