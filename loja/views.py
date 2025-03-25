from django.shortcuts import render, redirect
from .models import Produto
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login, authenticate, login, logout
from .forms import RegistroForm
from django.contrib.auth.decorators import login_required
from .decorators import staff_required
from django.contrib.auth.models import User

def home(request):
    produtos = Produto.objects.all()
    return render(request, 'loja/home.html', {'produtos': produtos})


def registrar(request):
    if request.method == "POST":
        form = RegistroForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.save()
            login(request, user)  # Faz login automaticamente após o cadastro
            return redirect('home')
    else:
        form = RegistroForm()
    return render(request, 'loja/registrar.html', {'form': form})

def entrar(request):
    if request.method == "POST":
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('home')
    else:
        form = AuthenticationForm()
    return render(request, 'loja/login.html', {'form': form})

def sair(request):
    logout(request)
    return redirect('home')

@staff_required
def dashboard(request):
    return render(request, 'loja/dashboard.html')