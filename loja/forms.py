from django import forms
from django.contrib.auth.models import User

class RegistroForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirme a senha", widget=forms.PasswordInput)
    is_superuser = forms.BooleanField(required=False, label="Tornar Superusuário")

    class Meta:
        model = User
        fields = ['username', 'email']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)  # Pega o usuário da view
        super().__init__(*args, **kwargs)
        
        # Se o usuário não for admin, remove o campo is_superuser
        if not (user and user.is_staff):
            del self.fields['is_superuser']

    def clean_password2(self):
        if self.cleaned_data['password'] != self.cleaned_data['password2']:
            raise forms.ValidationError("As senhas não coincidem!")
        return self.cleaned_data['password2']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        
        # Verifica se o admin marcou o campo para tornar superusuário
        if 'is_superuser' in self.cleaned_data and self.cleaned_data['is_superuser']:
            user.is_superuser = True
            user.is_staff = True  # O superusuário também deve ser staff
        if commit:
            user.save()
        return user
