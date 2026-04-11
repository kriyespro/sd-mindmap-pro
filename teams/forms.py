from django import forms

from teams.models import Team

_INVITE_WIDGET = {
    'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20',
    'placeholder': 'Existing user’s username',
    'autocomplete': 'username',
}


class TeamInviteForm(forms.Form):
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs=_INVITE_WIDGET))


class TeamCreateForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ('name',)
        widgets = {
            'name': forms.TextInput(
                attrs={
                    'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20',
                    'placeholder': 'e.g. Product, Marketing',
                    'maxlength': 120,
                }
            ),
        }
