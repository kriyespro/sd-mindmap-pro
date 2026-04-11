from django.urls import path

from billing import views

app_name = 'billing'

urlpatterns = [
    path('', views.BillingView.as_view(), name='overview'),
    path('plan/change/', views.PlanChangeView.as_view(), name='plan_change'),
]
