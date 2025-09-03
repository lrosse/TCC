from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test

# 🔹 Apenas admins podem acessar
def admin_required(user):
    return user.is_staff or user.is_superuser

@login_required
@user_passes_test(admin_required)
def gestao_index(request):
    return render(request, "loja/gestao/index.html")

@login_required
@user_passes_test(admin_required)
def gestao_estoque(request):
    return render(request, "loja/gestao/estoque.html")


