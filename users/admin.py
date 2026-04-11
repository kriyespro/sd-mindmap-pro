from datetime import date, timedelta

from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User

from users.models import Profile


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    fk_name = 'user'
    fields = ('plan', 'is_trial', 'trial_ends')


class UserAdmin(DjangoUserAdmin):
    inlines = (ProfileInline,)
    list_display = (*DjangoUserAdmin.list_display, 'trial_badge')
    list_filter = (*DjangoUserAdmin.list_filter, 'profile__is_trial')

    @admin.display(description='Trial')
    def trial_badge(self, obj: User) -> str:
        try:
            p = obj.profile
        except Profile.DoesNotExist:
            return '—'
        if not p.is_trial:
            return '—'
        end = p.trial_ends.isoformat() if p.trial_ends else 'open'
        return f'Yes (→ {end})'

    @admin.action(description='Mark as trial user (7 days from today)')
    def mark_trial_7_days(self, request, queryset):
        ends = date.today() + timedelta(days=7)
        for user in queryset:
            prof, _ = Profile.objects.get_or_create(user=user)
            prof.is_trial = True
            prof.trial_ends = ends
            prof.save()
        self.message_user(
            request,
            f'{queryset.count()} user(s) on trial until {ends.isoformat()}.',
            messages.SUCCESS,
        )

    @admin.action(description='Clear trial flag for selected users')
    def clear_trial(self, request, queryset):
        Profile.objects.filter(user__in=queryset).update(
            is_trial=False, trial_ends=None
        )
        self.message_user(request, 'Trial cleared.', messages.SUCCESS)

    actions = [*DjangoUserAdmin.actions, 'mark_trial_7_days', 'clear_trial']


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
