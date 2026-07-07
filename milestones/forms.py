from django import forms
from milestones.models import Milestone


class MilestoneForm(forms.ModelForm):
    class Meta:
        model = Milestone
        fields = ['name', 'description', 'due_date', 'status', 'progress']
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 2}),
            'progress': forms.NumberInput(attrs={'min': 0, 'max': 100}),
        }
