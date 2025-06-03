from django.shortcuts import render, redirect, get_object_or_404
from .models import Produto, Carrinho, ItemCarrinho
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login, authenticate, logout
from .forms import RegistroForm
from django.contrib.auth.decorators import login_required
from .decorators import staff_required
from django.contrib.auth.models import User

def home(request):
    produtos = Produto.objects.all()
    return render(request, 'loja/home.html', {'produtos': produtos})

def registrar(request):
    if request.method == "POST":
        form = RegistroForm(request.POST, user=request.user)  # Passa o usuário autenticado
        if form.is_valid():
            user = form.save()
            login(request, user)  # Faz login automaticamente após o cadastro
            return redirect('home')
    else:
        form = RegistroForm(user=request.user)  # Passa o usuário autenticado
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
    if request.method == "POST":
        form = RegistroForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            if 'make_superuser' in request.POST:
                user.is_superuser = True
                user.is_staff = True
            user.save()
            login(request, user)
            return redirect('home')
    else:
        form = RegistroForm()
    return render(request, 'loja/dashboard.html', {'form': form})

def criar_produto(request):
    if request.method == 'POST':
        nome = request.POST.get('nome')
        descricao = request.POST.get('descricao')
        preco = request.POST.get('preco')
        quantidade = request.POST.get('quantidade', 0)
        imagem = request.FILES.get('imagem')

        Produto.objects.create(
            nome=nome,
            descricao=descricao,
            preco=preco,
            quantidade=quantidade,
            imagem=imagem
        )
        return redirect('listar_produtos')

    return render(request, 'loja/criar_produto.html')

def listar_produtos(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect('login')
    produtos = Produto.objects.all()
    return render(request, 'loja/listar_produtos.html', {'produtos': produtos})

@staff_required
def editar_produto(request, produto_id):
    try:
        produto = Produto.objects.get(id=produto_id)
    except Produto.DoesNotExist:
        return redirect('listar_produtos')
    
    if request.method == 'POST':
        produto.nome = request.POST.get('nome')
        produto.descricao = request.POST.get('descricao')
        produto.preco = request.POST.get('preco')
        produto.quantidade = request.POST.get('quantidade', 0)
        if 'imagem' in request.FILES:
            produto.imagem = request.FILES['imagem']
        produto.save()
        return redirect('listar_produtos')
    
    return render(request, 'loja/editar_produto.html', {'produto': produto})

@staff_required
def excluir_produto(request, produto_id):
    try:
        produto = Produto.objects.get(id=produto_id)
    except Produto.DoesNotExist:
        return redirect('listar_produtos')
    
    if request.method == 'POST':
        produto.delete()
        return redirect('listar_produtos')
    
    return render(request, 'loja/excluir_produto.html', {'produto': produto})

# FUNÇÃO AUXILIAR SEM DECORATOR
def get_or_create_carrinho(usuario):
    carrinho, criado = Carrinho.objects.get_or_create(usuario=usuario)
    return carrinho

@login_required
def adicionar_ao_carrinho(request, produto_id):
    produto = get_object_or_404(Produto, id=produto_id)
    carrinho = get_or_create_carrinho(request.user)
    item_carrinho, criado = ItemCarrinho.objects.get_or_create(
        carrinho=carrinho,
        produto=produto,
        defaults={'preco_unitario': produto.preco, 'quantidade': 1}
    )
    if not criado:
        item_carrinho.quantidade += 1
        item_carrinho.save()
    carrinho.calcular_total()
    return redirect('ver_carrinho')

@login_required
def ver_carrinho(request):
    carrinho = get_or_create_carrinho(request.user)
    itens = ItemCarrinho.objects.filter(carrinho=carrinho)
    total = carrinho.valor_total
    return render(request, 'loja/carrinho.html', {'itens': itens, 'total': total})

@login_required
def remover_do_carrinho(request, item_id):
    item = get_object_or_404(ItemCarrinho, id=item_id, carrinho__usuario=request.user)
    item.delete()
    item.carrinho.calcular_total()
    return redirect('ver_carrinho')

@login_required
def alterar_quantidade(request, item_id):
    item = get_object_or_404(ItemCarrinho, id=item_id, carrinho__usuario=request.user)
    if request.method == "POST":
        qtd = int(request.POST.get('quantidade', 1))
        if qtd > 0:
            item.quantidade = qtd
            item.save()
        else:
            item.delete()
        item.carrinho.calcular_total()
    return redirect('ver_carrinho')
