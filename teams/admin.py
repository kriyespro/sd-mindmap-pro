from django.contrib import admin

from teams.models import Team, TeamMembership


class MembershipInline(admin.TabularInline):
    model = TeamMembership
    extra = 0


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_by', 'created_at')
    search_fields = ('name', 'slug')
    inlines = [MembershipInline]
