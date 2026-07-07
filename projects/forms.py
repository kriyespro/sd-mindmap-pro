from django import forms

from planner.models import Task
from projects.models import Project


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = [
            'name', 'description', 'status', 'priority', 'health',
            'client_name', 'budget', 'start_date', 'end_date', 'color', 'team',
        ]
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'color': forms.TextInput(attrs={'type': 'color'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Create modal does not expose these fields; model defaults apply on save.
        self.fields['health'].required = False
        self.fields['team'].required = False

    def clean_health(self):
        value = self.cleaned_data.get('health')
        return value or Project.HEALTH_ON_TRACK


class ProjectTaskCreateForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['title', 'start_date', 'due_date', 'priority', 'status']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500',
                'placeholder': 'Task title',
            }),
            'start_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500',
            }),
            'due_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500',
            }),
            'priority': forms.Select(attrs={
                'class': 'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500',
            }),
            'status': forms.Select(attrs={
                'class': 'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500',
            }),
        }
