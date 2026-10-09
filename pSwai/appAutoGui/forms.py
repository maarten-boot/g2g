from django.forms import (
    CharField,
    Form,
    # BooleanField,
    PasswordInput,
)


class LoginForm(Form):
    loginName = CharField()
    loginPassword = CharField(widget=PasswordInput)
    # loginCheck = BooleanField()
