from django import forms

from teams.models import Team, TeamInvite, TeamMembership

_INVITE_WIDGET = {
    'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20',
    'placeholder': 'Their login username',
    'autocomplete': 'username',
}


class TeamInviteForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={
                **_INVITE_WIDGET,
                'placeholder': 'e.g. alex',
                'autocomplete': 'username',
            }
        ),
    )
    role = forms.ChoiceField(
        choices=TeamMembership.ROLE_CHOICES,
        initial=TeamMembership.ROLE_MEMBER,
        widget=forms.Select(
            attrs={
                'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20'
            }
        ),
    )


class TeamJoinLinkForm(forms.Form):
    role = forms.ChoiceField(
        choices=TeamInvite.ROLE_CHOICES,
        initial=TeamInvite.ROLE_MEMBER,
        widget=forms.Select(
            attrs={
                'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20'
            }
        ),
    )


class TeamCreateForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ('name', 'sidebar_color')
        widgets = {
            'name': forms.TextInput(
                attrs={
                    'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20',
                    'placeholder': 'e.g. Product, Marketing',
                    'maxlength': 120,
                }
            ),
            'sidebar_color': forms.Select(
                attrs={
                    'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20'
                }
            )
        }


class TeamSidebarSettingsForm(forms.Form):
    sidebar_color = forms.ChoiceField(
        choices=Team.COLOR_CHOICES,
        widget=forms.Select(
            attrs={
                'class': 'rounded border border-slate-200 bg-white px-1.5 py-1 text-[10px] text-slate-600 focus:border-indigo-500 focus:outline-none'
            }
        ),
    )
