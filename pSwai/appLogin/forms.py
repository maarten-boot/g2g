from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class SignupForm(UserCreationForm):  # pylint:disable=R0901; type: ignore
    class Meta:  # pylint:disable=R0903
        model = User
        fields = [
            "username",
            "password1",
            "password2",
        ]


class LoginForm(forms.Form):
    username = forms.CharField()
    password = forms.CharField(widget=forms.PasswordInput)
