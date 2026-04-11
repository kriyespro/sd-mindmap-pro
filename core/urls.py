import core.admin  # noqa: F401 — register branding before urlpatterns
from django.contrib import admin
from django.urls import include, path
from users.views import LandingView

from core.views import health

urlpatterns = [
    path('health/', health, name='health'),
    path('', LandingView.as_view(), name='landing'),
    path('admin/', include('staff_dashboard.urls')),
    path('sd/', admin.site.urls),
    path('billing/', include('billing.urls')),
    path('', include('planner.urls')),
    path('', include('users.urls')),
    path('teams/', include('teams.urls')),
]
