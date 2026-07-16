from django import forms

from teams.models import Team, TeamInvite, TeamMembership

_FIELD = (
    'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm '
    'focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20'
)


class TeamInviteForm(forms.Form):
    """One primary field: username OR email. Legacy fields still accepted."""

    who = forms.CharField(
        max_length=254,
        required=False,
        widget=forms.TextInput(
            attrs={
                'class': _FIELD,
                'placeholder': 'Username or email',
                'autocomplete': 'off',
            }
        ),
    )
    username = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.HiddenInput(),
    )
    email = forms.EmailField(
        required=False,
        widget=forms.HiddenInput(),
    )
    full_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.HiddenInput(),
    )
    role = forms.ChoiceField(
        choices=TeamMembership.ROLE_CHOICES,
        initial=TeamMembership.ROLE_MEMBER,
        widget=forms.Select(attrs={'class': _FIELD}),
    )

    def clean(self):
        cleaned = super().clean()
        who = (cleaned.get('who') or '').strip()
        username = (cleaned.get('username') or '').strip()
        email = (cleaned.get('email') or '').strip().lower()

        if who:
            if '@' in who:
                email = who.lower()
                username = ''
            else:
                username = who
                email = ''

        cleaned['username'] = username
        cleaned['email'] = email
        if not username and not email:
            raise forms.ValidationError('Enter a username or email')
        return cleaned


class TeamJoinLinkForm(forms.Form):
    role = forms.ChoiceField(
        choices=TeamInvite.ROLE_CHOICES,
        initial=TeamInvite.ROLE_MEMBER,
        widget=forms.Select(attrs={'class': _FIELD}),
    )


class TeamCreateForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ('name', 'sidebar_color')
        widgets = {
            'name': forms.TextInput(
                attrs={
                    'class': _FIELD,
                    'placeholder': 'e.g. Product, Marketing',
                    'maxlength': 120,
                }
            ),
            'sidebar_color': forms.Select(attrs={'class': _FIELD}),
        }


class TeamSidebarSettingsForm(forms.Form):
    sidebar_color = forms.ChoiceField(
        choices=Team.COLOR_CHOICES,
        widget=forms.Select(
            attrs={
                'class': (
                    'rounded border border-slate-200 bg-white px-1.5 py-1 '
                    'text-[10px] text-slate-600 focus:border-indigo-500 focus:outline-none'
                )
            }
        ),
    )
