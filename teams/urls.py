from django.urls import path

from teams.views import (
    TeamCreateView,
    TeamInviteAcceptView,
    TeamInviteView,
    TeamJoinLinkGenerateView,
    TeamMemberAddView,
    TeamMemberRemoveView,
    TeamMemberStatusView,
)

app_name = 'teams'

urlpatterns = [
    path('create/', TeamCreateView.as_view(), name='create'),
    path('<slug:team_slug>/invite/', TeamInviteView.as_view(), name='invite'),
    path('<slug:team_slug>/invite-link/', TeamJoinLinkGenerateView.as_view(), name='invite_link'),
    path('<slug:team_slug>/members/add/', TeamMemberAddView.as_view(), name='member_add'),
    path(
        '<slug:team_slug>/members/<int:membership_id>/remove/',
        TeamMemberRemoveView.as_view(),
        name='member_remove',
    ),
    path(
        '<slug:team_slug>/members/<int:membership_id>/status/',
        TeamMemberStatusView.as_view(),
        name='member_status',
    ),
    path('join/<str:token>/', TeamInviteAcceptView.as_view(), name='accept_invite'),
]
