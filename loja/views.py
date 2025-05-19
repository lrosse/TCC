from django.shortcuts import render, redirect
from .models import Produto
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
            # Cria o novo usuário sem salvar no banco ainda
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            
            # Verifica se o admin selecionou a opção de ser superuser
            if 'make_superuser' in request.POST:
                user.is_superuser = True
                user.is_staff = True  # Tornando o usuário um admin, se for o caso

            user.save()
            login(request, user)  # Faz login automaticamente após o cadastro
            return redirect('home')
    else:
        form = RegistroForm()

    return render(request, 'loja/dashboard.html', {'form': form})

def criar_produto(request):
    if request.method == 'POST':
        nome = request.POST.get('nome')
        descricao = request.POST.get('descricao')
        preco = request.POST.get('preco')
        quantidade = request.POST.get('quantidade', 0)  # Valor padrão 0 se não for fornecido
        imagem = request.FILES.get('imagem')

        Produto.objects.create(
            nome=nome,
            descricao=descricao,
            preco=preco,
            quantidade=quantidade,  # Campo adicionado
            imagem=imagem
        )
        return redirect('listar_produtos')  # Redireciona para a lista de produtos

    return render(request, 'loja/criar_produto.html')

def listar_produtos(request):
    # Verificar se o usuário está autenticado e é staff
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect('login')
    
    # Buscar todos os produtos
    produtos = Produto.objects.all()
    
    # Renderizar o template com os produtos
    context = {
        'produtos': produtos
    }
    return render(request, 'loja/listar_produtos.html', context)
    
@staff_required
def editar_produto(request, produto_id):
    # Buscar o produto pelo ID ou retornar 404 se não existir
    try:
        produto = Produto.objects.get(id=produto_id)
    except Produto.DoesNotExist:
        return redirect('listar_produtos')
    
    if request.method == 'POST':
        # Atualizar os dados do produto
        produto.nome = request.POST.get('nome')
        produto.descricao = request.POST.get('descricao')
        produto.preco = request.POST.get('preco')
        produto.quantidade = request.POST.get('quantidade', 0)
        
        # Verificar se uma nova imagem foi enviada
        if 'imagem' in request.FILES:
            produto.imagem = request.FILES['imagem']
            
        # Salvar as alterações
        produto.save()
        return redirect('listar_produtos')
    
    # Renderizar o formulário de edição com os dados do produto
    context = {
        'produto': produto
    }
    return render(request, 'loja/editar_produto.html', context)

@staff_required
def excluir_produto(request, produto_id):
    # Buscar o produto pelo ID
    try:
        produto = Produto.objects.get(id=produto_id)
    except Produto.DoesNotExist:
        return redirect('listar_produtos')
    
    if request.method == 'POST':
        # Excluir o produto
        produto.delete()
        return redirect('listar_produtos')
    
    # Renderizar a página de confirmação
    context = {
        'produto': produto
    }
    return render(request, 'loja/excluir_produto.html', context)