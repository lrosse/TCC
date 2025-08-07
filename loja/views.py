from django.shortcuts import render, redirect, get_object_or_404
from .models import Produto, Carrinho, ItemCarrinho, Pedido, PedidoItem
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login, authenticate, logout
from .forms import RegistroForm
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from .decorators import staff_required
from django.contrib.auth.models import User
from django.contrib import messages
from .models import EntradaEstoque
from .models import MovimentacaoEstoque  
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db.models import Q

def home(request):
    produtos = Produto.objects.all()

    # Pegando os parâmetros da URL
    termo_busca = request.GET.get('q')
    preco_min = request.GET.get('preco_min')
    preco_max = request.GET.get('preco_max')

    # Filtro por nome (busca)
    if termo_busca:
        produtos = produtos.filter(nome__icontains=termo_busca)

    # Filtro por faixa de preço
    if preco_min:
        produtos = produtos.filter(preco__gte=preco_min)
    if preco_max:
        produtos = produtos.filter(preco__lte=preco_max)

    context = {
        'produtos': produtos,
    }
    return render(request, 'loja/home.html', context)

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

@staff_required
def listar_produtos(request):
    nome = request.GET.get("nome", "")
    preco = request.GET.get("preco", "")
    descricao = request.GET.get("descricao", "")
    quantidade = request.GET.get("quantidade", "")

    produtos = Produto.objects.all()

    if nome:
        produtos = produtos.filter(nome__icontains=nome)
    if preco:
        produtos = produtos.filter(preco__icontains=preco)
    if descricao:
        produtos = produtos.filter(descricao__icontains=descricao)
    if quantidade:
        produtos = produtos.filter(quantidade__icontains=quantidade)

    context = {
        "produtos": produtos,
        "nome": nome,
        "preco": preco,
        "descricao": descricao,
        "quantidade": quantidade,
    }
    return render(request, "loja/listar_produtos.html", context)
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

def produto_detalhe(request, produto_id):
    produto = get_object_or_404(Produto, id=produto_id)
    return render(request, 'loja/produto_detalhe.html', {'produto': produto})

@staff_required
def entrada_estoque(request):
    produtos = Produto.objects.all().order_by('nome')

    if request.method == 'POST':
        produto_id = request.POST.get('produto_id')
        quantidade = request.POST.get('quantidade')
        observacao = request.POST.get('observacao', '')

        try:
            produto = Produto.objects.get(id=produto_id) 
            quantidade = int(quantidade)

            if quantidade <= 0:
                messages.error(request, "A quantidade deve ser maior que zero.")
            else:
                produto.quantidade += quantidade
                produto.save()

                MovimentacaoEstoque.objects.create(
                    produto=produto,
                    tipo='entrada',
                    quantidade=quantidade,
                    estoque_final=produto.quantidade,
                    observacao=observacao or f"Entrada registrada por {request.user.username}"
                )

                messages.success(request, f"Entrada de {quantidade} unidades para '{produto.nome}' registrada com sucesso.")
                return redirect('entrada_estoque')

        except Produto.DoesNotExist:
            messages.error(request, "Produto não encontrado.")
        except ValueError:
            messages.error(request, "Quantidade inválida.")

    return render(request, 'loja/entrada_estoque.html', {'produtos': produtos})


@staff_required
def ajuste_estoque(request):
    produtos = Produto.objects.all().order_by('nome')

    if request.method == 'POST':
        produto_id = request.POST.get('produto_id')
        nova_quantidade = request.POST.get('nova_quantidade')
        observacao = request.POST.get('observacao', '')

        try:
            produto = Produto.objects.get(id=produto_id)
            nova_quantidade = int(nova_quantidade)

            if nova_quantidade < 0:
                messages.error(request, "A quantidade não pode ser negativa.")
                return redirect('ajuste_estoque')

            produto.quantidade = nova_quantidade
            produto.save()

            MovimentacaoEstoque.objects.create(
                produto=produto,
                tipo='ajuste',
                quantidade=nova_quantidade,
                estoque_final=produto.quantidade,
                observacao=observacao or f"Ajuste manual realizado por {request.user.username}"
            )

            messages.success(request, f"Estoque de '{produto.nome}' atualizado para {nova_quantidade}.")
            return redirect('ajuste_estoque')

        except Produto.DoesNotExist:
            messages.error(request, "Produto não encontrado.")
        except ValueError:
            messages.error(request, "Quantidade inválida.")

    return render(request, 'loja/ajuste_estoque.html', {'produtos': produtos})



@staff_required
def historico_estoque(request):
    movimentacoes = MovimentacaoEstoque.objects.select_related('produto').order_by('-data')
    return render(request, 'loja/historico_estoque.html', {'movimentacoes': movimentacoes})

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

@login_required
def finalizar_compra(request):
    try:
        carrinho = Carrinho.objects.get(usuario=request.user)
        itens = carrinho.itemcarrinho_set.all()
    except Carrinho.DoesNotExist:
        messages.error(request, "Seu carrinho está vazio.")
        return redirect('ver_carrinho')

    if not itens:
        messages.warning(request, "Seu carrinho está vazio.")
        return redirect('ver_carrinho')

    if request.method == 'POST':
        # Captura os dados do formulário
        nome = request.POST.get("nome")
        rua = request.POST.get("rua")
        numero = request.POST.get("numero")
        bairro = request.POST.get("bairro")
        cidade = request.POST.get("cidade")
        complemento = request.POST.get("complemento", "")
        referencia = request.POST.get("referencia", "")

        # Cria o pedido
        pedido = Pedido.objects.create(
            cliente=request.user,
            total=carrinho.total(),
            status='Pendente'
        )

        # Cria os itens do pedido
        for item in itens:
            PedidoItem.objects.create(
                pedido=pedido,
                produto=item.produto,
                quantidade=item.quantidade,
                preco_unitario=item.preco_unitario
            )

        # Limpa o carrinho
        itens.delete()
        carrinho.valor_total = 0
        carrinho.save()

        # Monta a mensagem do WhatsApp
        mensagem = "🛒 *Pedido realizado através do site*:%0A%0A"
        mensagem += "📦 *Produtos:*%0A"

        for item in pedido.itens.all():
            mensagem += f"- {item.quantidade}x {item.produto.nome} – R$ {item.subtotal()}%0A"

        mensagem += f"%0A💰 *Total:* R$ {pedido.total}%0A%0A"
        mensagem += "📍 *Endereço de entrega:*%0A"
        mensagem += f"{rua}, {numero}%0A{bairro} – {cidade}%0A"
        if complemento:
            mensagem += f"Complemento: {complemento}%0A"
        if referencia:
            mensagem += f"Referência: {referencia}%0A"
        mensagem += f"%0A🙋 Cliente: {nome}%0A"
        mensagem += "Agradeço desde já e fico no aguardo da confirmação 😊"

        numero_vendedor = '5518988083436'
        url = f"https://wa.me/{numero_vendedor}?text={mensagem}"

        return redirect(url)

    # GET – Exibe a página
    total = carrinho.total()
    numero_vendedor = '5518988083436'
    return render(request, 'loja/finalizar_compra.html', {
        'itens': itens,
        'total': total,
        'numero_vendedor': numero_vendedor
    })



@staff_required
def pedidos(request):
    from .models import Pedido  # Garante importação segura

    # Filtros
    termo_nome = request.GET.get("nome", "")
    status = request.GET.get("status", "")
    valor = request.GET.get("valor", "")
    data = request.GET.get("data", "")

    pedidos = Pedido.objects.select_related("cliente").order_by("-data_criacao")

    if termo_nome:
        pedidos = pedidos.filter(cliente__username__icontains=termo_nome)
    if status:
        pedidos = pedidos.filter(status=status)
    if valor:
        pedidos = pedidos.filter(total__icontains=valor)
    if data:
        pedidos = pedidos.filter(data_criacao__date=data)

    context = {
        "pedidos": pedidos,
        "filtros": {
            "nome": termo_nome,
            "status": status,
            "valor": valor,
            "data": data
        }
    }
    return render(request, "loja/pedidos.html", context)

@staff_required
def detalhes_pedido(request, pedido_id):
    from .models import Pedido
    pedido = get_object_or_404(Pedido, id=pedido_id)
    itens = pedido.itens.all()

    # Verifica se o formulário foi enviado
    if request.method == "POST":
        novo_status = request.POST.get("status")
        if novo_status in ["Pendente", "Pago", "Cancelado"]:
            pedido.status = novo_status
            pedido.save()
            messages.success(request, f"Status do pedido atualizado para '{novo_status}'.")
            return redirect('detalhes_pedido', pedido_id=pedido.id)
        else:
            messages.error(request, "Status inválido.")

    return render(request, "loja/detalhes_pedido.html", {
        "pedido": pedido,
        "itens": itens
    })

@staff_required
@require_POST
def atualizar_status_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id)
    novo_status = request.POST.get("status")

    if novo_status in ["Pendente", "Pago", "Cancelado"]:
        pedido.status = novo_status
        pedido.save()
        messages.success(request, f"Status do pedido #{pedido.id} atualizado para '{novo_status}'.")
    else:
        messages.error(request, "Status inválido.")

    return redirect("pedidos")
    