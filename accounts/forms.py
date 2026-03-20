from django import forms
from django.contrib.auth.forms import AuthenticationForm
from .models import User
from tickets.models import Mall


class ExternalRegisterForm(forms.ModelForm):
    password1 = forms.CharField(widget=forms.PasswordInput, label='Password')
    password2 = forms.CharField(widget=forms.PasswordInput, label='Confirm Password')

    class Meta:
        model = User
        fields = ['full_name', 'email', 'mobile', 'business_name', 'project']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['project'].queryset = Mall.objects.filter(is_active=True)
        self.fields['project'].label = 'Mall / Project'
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-input'})

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('password1') != cleaned.get('password2'):
            raise forms.ValidationError("Passwords do not match.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.EXTERNAL
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class InternalUserCreateForm(forms.ModelForm):
    """Used by Admin to create internal users"""
    password = forms.CharField(widget=forms.PasswordInput, label='Temporary Password')

    class Meta:
        model = User
        fields = ['full_name', 'email', 'mobile', 'role', 'department']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['role'].choices = [
            (User.INTERNAL, 'Internal User'),
            (User.MANAGER,  'Manager'),
        ]
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-input'})

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    username = forms.EmailField(label='Email Address', widget=forms.EmailInput(attrs={'class': 'form-input', 'autofocus': True}))
    password = forms.CharField(label='Password', widget=forms.PasswordInput(attrs={'class': 'form-input'}))
