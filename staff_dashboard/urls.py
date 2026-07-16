from django.urls import path

from staff_dashboard import views

app_name = 'staff_dashboard'

urlpatterns = [
    path('', views.StaffDashboardView.as_view(), name='dashboard'),
    path('stats/', views.StaffStatsPartialView.as_view(), name='stats'),
    path('users/', views.StaffUsersView.as_view(), name='users'),
    path('users/partial/', views.StaffUsersPartialView.as_view(), name='users_partial'),
    path('users/<int:user_id>/', views.StaffUserDetailView.as_view(), name='user_detail'),
    path('users/<int:user_id>/plan/', views.StaffUserPlanView.as_view(), name='user_plan'),
    path('users/<int:user_id>/trial/', views.StaffUserTrialView.as_view(), name='user_trial'),
    path('users/<int:user_id>/active/', views.StaffUserActiveView.as_view(), name='user_active'),
    path('users/<int:user_id>/convert/', views.StaffUserConvertView.as_view(), name='user_convert'),
]
