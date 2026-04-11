from datetime import datetime

from django import forms

from planner.models import Task


class TaskCreateForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ('title', 'due_date', 'assignee_username')
        widgets = {
            'title': forms.TextInput(
                attrs={
                    'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm',
                    'placeholder': 'What needs to be done?',
                }
            ),
            'due_date': forms.DateInput(
                attrs={'type': 'date', 'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm'}
            ),
            'assignee_username': forms.TextInput(
                attrs={
                    'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm',
                    'placeholder': 'Username',
                }
            ),
        }


class TaskTitleForm(forms.Form):
    title = forms.CharField(max_length=500)


class TaskMetaForm(forms.Form):
    due_date = forms.CharField(required=False)
    assignee_username = forms.CharField(max_length=150, required=False)

    def clean_due_date(self):
        raw = (self.cleaned_data.get('due_date') or '').strip()
        if not raw:
            return None
        try:
            return datetime.strptime(raw, '%Y-%m-%d').date()
        except ValueError as e:
            raise forms.ValidationError('Invalid date') from e


class TaskImportForm(forms.Form):
    file = forms.FileField(
        widget=forms.ClearableFileInput(
            attrs={
                'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-xs text-slate-700 file:mr-3 file:rounded-md file:border-0 file:bg-indigo-50 file:px-2.5 file:py-1 file:text-xs file:font-semibold file:text-indigo-700 hover:file:bg-indigo-100',
                'accept': '.csv,.txt,text/csv,text/plain',
            }
        )
    )

    def clean_file(self):
        f = self.cleaned_data['file']
        name = (f.name or '').lower()
        if not (name.endswith('.csv') or name.endswith('.txt')):
            raise forms.ValidationError('Upload a .csv or .txt file')
        return f
