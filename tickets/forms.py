from django import forms
from .models import Ticket, TicketUpdate, SubCategory, Department
from django.contrib.auth import get_user_model

User = get_user_model()


class TicketCreateForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = [
            'mall', 'ticket_type', 'department', 'sub_category', 'priority',
            'complainant_name', 'complainant_company', 'complainant_address',
            'due_date', 'complaint_description',
        ]
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'complaint_description': forms.Textarea(attrs={'rows': 4}),
            'complainant_address': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if self.user and self.user.is_external:
            if self.user.project:
                self.fields['mall'].initial = self.user.project
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-input'})

    def save(self, commit=True):
        ticket = super().save(commit=False)
        if self.user:
            ticket.created_by = self.user
        if commit:
            ticket.save()
        return ticket


class TicketAssignForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['assigned_to', 'ticket_status']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show internal users in the assignee dropdown
        self.fields['assigned_to'].queryset = User.objects.filter(
            role__in=[User.INTERNAL, User.MANAGER],
            is_active=True
        )
        self.fields['assigned_to'].label = 'Assign To'
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-input'})


class TicketUpdateForm(forms.ModelForm):
    class Meta:
        model = TicketUpdate
        fields = ['note']
        widgets = {'note': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Add update note…'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['note'].widget.attrs.update({'class': 'form-input'})


class TicketResolveForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['resolution']
        widgets = {'resolution': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Describe the resolution…'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['resolution'].widget.attrs.update({'class': 'form-input'})


class TicketEditForm(forms.ModelForm):
    """External users can only edit title (description) before it is assigned"""
    class Meta:
        model = Ticket
        fields = ['complaint_description', 'complainant_address']
        widgets = {
            'complaint_description': forms.Textarea(attrs={'rows': 4}),
            'complainant_address': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-input'})


class TicketFilterForm(forms.Form):
    status   = forms.ChoiceField(choices=[('', 'All Statuses')] + Ticket.STATUS_CHOICES, required=False)
    priority = forms.ChoiceField(choices=[('', 'All Priorities')] + Ticket.PRIORITY_CHOICES, required=False)
    dept     = forms.ModelChoiceField(queryset=Department.objects.filter(is_active=True), required=False, empty_label='All Departments')
    search   = forms.CharField(required=False, widget=forms.TextInput(attrs={'placeholder': 'Search tickets…'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-input'})