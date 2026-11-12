from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Team


class SignupForm(UserCreationForm):
    email = forms.EmailField(label='E-Mail', required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')


class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ('name', 'description', 'is_public')
        widgets = {'name': forms.TextInput(attrs={'placeholder': 'z. B. Mein Champions-Team'})}
