from django.urls import path

from teams.views import TeamCreateView, TeamInviteView

app_name = 'teams'

urlpatterns = [
    path('create/', TeamCreateView.as_view(), name='create'),
    path('<slug:team_slug>/invite/', TeamInviteView.as_view(), name='invite'),
]
