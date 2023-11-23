from django.forms import (
    Form,
    CharField,
    # BooleanField,
    PasswordInput,
)


class LoginForm(Form):
    loginName = CharField()
    loginPassword = CharField(widget=PasswordInput)
    # loginCheck = BooleanField()
