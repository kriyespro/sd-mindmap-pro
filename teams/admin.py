from django.contrib import admin

from teams.models import Team, TeamInvite, TeamMembership


class MembershipInline(admin.TabularInline):
    model = TeamMembership
    extra = 0


class InviteInline(admin.TabularInline):
    model = TeamInvite
    extra = 0
    readonly_fields = ('token', 'created_at', 'accepted_at')


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_by', 'created_at')
    search_fields = ('name', 'slug')
    inlines = [MembershipInline, InviteInline]
