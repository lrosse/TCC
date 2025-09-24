from django.shortcuts import render, redirect, get_object_or_404
from .models import Produto, Carrinho, ItemCarrinho, Pedido, PedidoItem, Feedback
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login, authenticate, logout
from .forms import RegistroForm, FeedbackForm
from django.views.decorators.http import require_POST
from .decorators import staff_required
from django.contrib.auth.models import User
from django.contrib import messages
from .models import MovimentacaoEstoque
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db.models import Sum, Count, Avg, Max
from django.db import transaction
from urllib.parse import quote
from decimal import Decimal
from django.utils import timezone
from django.db.models.functions import ExtractMonth, ExtractDay 
from calendar import monthrange
from django.db.models.functions import ExtractMonth, ExtractDay, Coalesce
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.conf import settings
from urllib.parse import quote
from decimal import Decimal
from django.http import JsonResponse
from django.core.paginator import Paginator


# 👇 extras para serializar dados pro Chart.js
import json
from calendar import month_name
from calendar import monthrange
from django.db.models import Avg
from django.shortcuts import render
from .models import Produto

def home(request):
    produtos = Produto.objects.annotate(media_nota=Avg("feedbacks__nota"))
    produtos = Produto.objects.all().order_by("-id")

    termo_busca = request.GET.get('q')
    preco_min = request.GET.get('preco_min')
    preco_max = request.GET.get('preco_max')
    nota_min = request.GET.get('nota_min')
    paginator = Paginator(produtos, 12)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    if termo_busca:
        produtos = produtos.filter(nome__icontains=termo_busca)

    if preco_min:
        produtos = produtos.filter(preco__gte=preco_min)
    if preco_max:
        produtos = produtos.filter(preco__lte=preco_max)

    if nota_min:
        produtos = produtos.filter(media_nota__gte=nota_min)

    context = {
        'produtos': produtos,
        'filtros': {
            'q': termo_busca or '',
            'preco_min': preco_min or '',
            'preco_max': preco_max or '',
            'nota_min': nota_min or '',
        }
    }
    return render(request, "loja/home.html", {
        "page_obj": page_obj,
        "produtos": page_obj,   # para compatibilidade com o template atual
    })

def buscar_produtos(request):
    termo = request.GET.get("q", "").strip()
    resultados = []

    if termo:
        produtos = Produto.objects.filter(nome__icontains=termo)[:10]
        for p in produtos:
            resultados.append({
                "id": p.id,
                "nome": p.nome,
                "imagem": p.imagem.url if p.imagem else None,
                "url": f"/produto/{p.id}/"
            })

    return JsonResponse(resultados, safe=False)

def registrar(request):
    next_url = request.GET.get("next") or request.POST.get("next")

    if request.method == "POST":
        form = RegistroForm(request.POST, user=request.user)
        if form.is_valid():
            user = form.save()
            login(request, user)

            # 🔄 Migra carrinho da sessão para o banco
            migrar_carrinho_sessao_para_usuario(request, user)

            # 🔹 Recalcula contador da navbar pelo banco
            carrinho = get_or_create_carrinho(user)
            request.session["carrinho_itens"] = sum(i.quantidade for i in carrinho.itemcarrinho_set.all())
            request.session.modified = True

            # 🔀 Redireciona para origem, se existir
            return redirect(next_url or 'home')
    else:
        form = RegistroForm(user=request.user)

    return render(request, 'loja/registrar.html', {
        'form': form,
        'next': next_url
    })


def entrar(request):
    next_url = request.GET.get("next") or request.POST.get("next")

    if request.method == "POST":
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            # 🔄 Migra carrinho da sessão para o banco
            migrar_carrinho_sessao_para_usuario(request, user)

            # 🔹 Recalcula contador da navbar pelo banco
            carrinho = get_or_create_carrinho(user)
            request.session["carrinho_itens"] = sum(i.quantidade for i in carrinho.itemcarrinho_set.all())
            request.session.modified = True

            # 🔀 Redireciona para origem, se existir
            return redirect(next_url or 'home')
    else:
        form = AuthenticationForm()

    return render(request, 'loja/login.html', {
        'form': form,
        'next': next_url
    })
def sair(request):
    logout(request)
    return redirect('home')


# -------------------------------
# 🔧 HELPERS DE RELATÓRIOS
# -------------------------------

def _agregar_vendas_por_mes(queryset):
    """
    Soma total por mês do ANO ATUAL sem usar TruncMonth (evita problema de timezone no MySQL).
    """
    hoje = timezone.localdate()
    ano = hoje.year

    labels = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']
    values = [0.0] * 12

    agregados = (
        queryset
        .filter(data_criacao__year=ano)
        .annotate(mes_num=ExtractMonth('data_criacao'))   # 1..12
        .values('mes_num')
        .annotate(total=Sum('total'))
        .order_by('mes_num')
    )

    for row in agregados:
        m = (row['mes_num'] or 0)
        if 1 <= m <= 12:
            values[m - 1] = float(row['total'] or 0)

    return labels, values

def _agregar_vendas_mes_atual_por_dia(queryset):
    agora = timezone.now()
    ano = agora.year
    mes = agora.month
    dias_no_mes = monthrange(ano, mes)[1]  # Quantos dias tem o mês atual

    # Cria um dicionário com todos os dias do mês inicializados em 0
    vendas_dict = {dia: 0 for dia in range(1, dias_no_mes + 1)}

    # Busca vendas pagas do mês e soma por dia
    vendas_por_dia = (
        queryset.filter(
            data_criacao__year=ano,
            data_criacao__month=mes
        )
        .annotate(dia=ExtractDay('data_criacao'))
        .values('dia')
        .annotate(total=Sum('total'))
    )

    # Atualiza os valores do dicionário
    for venda in vendas_por_dia:
        dia = venda['dia']
        if dia:
            vendas_dict[dia] = float(venda['total'] or 0)

    # Converte para listas (labels e valores)
    labels = [f"{dia:02d}" for dia in vendas_dict.keys()]
    valores = list(vendas_dict.values())

    return labels, valores

def _contagem_pedidos_por_status(queryset):
    """
    Conta pedidos por status (Pendente, Pago, Cancelado...).
    Retorna labels e values para gráfico de pizza.
    """
    agregados = queryset.values('status').annotate(qtd=Count('id')).order_by()
    labels = [row['status'] or 'Indef.' for row in agregados]
    values = [row['qtd'] for row in agregados]
    return labels, values


@staff_required
def dashboard(request):
    """
    Dashboard administrativo com mini-gráfico do mês e resumos.
    """

    # Formulário de registro de usuário (já estava no seu código)
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

    agora = timezone.now()
    inicio_mes = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Total de vendas do mês (somente pedidos pagos)
    vendas_mes = (
        Pedido.objects
        .filter(status='Pago', data_criacao__gte=inicio_mes)
        .aggregate(total=Sum('total'))
        .get('total') or 0
    )

    # Filtra apenas pedidos pagos do mês atual
    pedidos_pagos = Pedido.objects.filter(status='Pago')

    # Gera os dados para o mini gráfico
    mini_labels, mini_values = _agregar_vendas_mes_atual_por_dia(pedidos_pagos)

    # DEBUG
    print(f"🔍 Dashboard DEBUG:")
    print(f"   Pedidos pagos total: {pedidos_pagos.count()}")
    print(f"   Mini labels: {mini_labels[:5]}...")
    print(f"   Mini values: {mini_values[:5]}...")
    print(f"   Vendas mês: {vendas_mes}")

    # Resumo dos pedidos
    pedidos_pendentes = Pedido.objects.filter(status="Pendente").count()
    pedidos_pagos = Pedido.objects.filter(status="Pago").count()
    pedidos_cancelados = Pedido.objects.filter(status="Cancelado").count()

    # Últimos 3 pedidos
    ultimos_pedidos = Pedido.objects.select_related("cliente").order_by("-data_criacao")[:3]

    # Top 5 produtos mais vendidos (somando quantidades em PedidoItem)
    top_produtos = (
        PedidoItem.objects
        .values("produto__nome")
        .annotate(
        total_vendido=Sum("quantidade"),
        ultima_venda=Max("pedido__data_criacao")  # 👈 pega a última vez vendido
    )
        .order_by("-total_vendido")[:5]
    )

    # 🔹 Últimos feedbacks (exibir 5 últimos)
    feedbacks = (
        Feedback.objects
        .select_related("usuario", "produto")
        .order_by("-data_criacao")[:5]
    )
    # Contexto enviado para o template
    ctx = {
        'form': form,
        'vendas_mes': vendas_mes,
        'mini_mes_labels_json': json.dumps(mini_labels, ensure_ascii=False),
        'mini_mes_values_json': json.dumps(mini_values),
        "pedidos_pendentes": pedidos_pendentes,
        "pedidos_pagos": pedidos_pagos,
        "pedidos_cancelados": pedidos_cancelados,
        "ultimos_pedidos": ultimos_pedidos,
        "top_produtos": top_produtos,  # 👈 adicionado
        "feedbacks": feedbacks,  # 👈 agora vai para o template
    }

    return render(request, 'loja/dashboard.html', ctx)

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
    # Pegando parâmetros da URL
    nome = request.GET.get("nome", "")
    produto_id = request.GET.get("id", "")
    preco_min = request.GET.get("preco_min", "")
    preco_max = request.GET.get("preco_max", "")
    quantidade_min = request.GET.get("quantidade_min", "")
    quantidade_max = request.GET.get("quantidade_max", "")

    produtos = Produto.objects.all()

    # Filtros
    if nome:
        produtos = produtos.filter(nome__icontains=nome)

    if produto_id:
        produtos = produtos.filter(id=produto_id)

    if preco_min:
        produtos = produtos.filter(preco__gte=preco_min)
    if preco_max:
        produtos = produtos.filter(preco__lte=preco_max)

    if quantidade_min:
        produtos = produtos.filter(quantidade__gte=quantidade_min)
    if quantidade_max:
        produtos = produtos.filter(quantidade__lte=quantidade_max)

    context = {
        "produtos": produtos,
        "nome": nome,
        "id": produto_id,
        "preco_min": preco_min,
        "preco_max": preco_max,
        "quantidade_min": quantidade_min,
        "quantidade_max": quantidade_max,
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

    if request.user.is_staff:  
        # Admin vê todos os feedbacks
        feedbacks = produto.feedbacks.select_related("usuario").order_by("-data_criacao")
    else:
        # Clientes só veem feedbacks aprovados
        feedbacks = produto.feedbacks.filter(visivel=True).select_related("usuario").order_by("-data_criacao")

    media_nota = feedbacks.aggregate(Avg("nota"))["nota__avg"] or 0
    media_nota = round(media_nota, 1)

    context = {
        "produto": produto,
        "feedbacks": feedbacks,
        "media_nota": media_nota,
    }
    return render(request, "loja/produto_detalhe.html", context)

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
    """
    Ajuste manual em lote.
    - Modo global: 'entrada' ou 'saida'
    - Quantidades por produto: name="qtd_<id>"
    - Observação: usa obs_<id> (se vier) ou cai no global 'observacao'
    """
    produtos = Produto.objects.all().order_by('nome')

    if request.method == 'POST':
        modo = (request.POST.get('acao_global') or 'entrada').strip().lower()
        if modo not in ('entrada', 'saida'):
            messages.error(request, "Modo inválido. Selecione Entrada ou Saída.")
            return redirect('ajuste_estoque')

        # Observação global do textarea (pode estar vazia)
        observacao_global = (request.POST.get('observacao') or '').strip()

        # Lista de (produto, qtd, observacao_efetiva)
        movimentos = []
        for p in produtos:
            qtd_raw = (request.POST.get(f'qtd_{p.id}') or '').strip()
            if not qtd_raw:
                continue
            try:
                qtd = int(qtd_raw)
            except ValueError:
                continue
            if qtd <= 0:
                continue

            # Preferência: obs_<id> se vier; caso contrário, usa a global
            obs_item = (request.POST.get(f'obs_{p.id}') or '').strip()
            obs_efetiva = obs_item if obs_item else observacao_global

            movimentos.append((p, qtd, obs_efetiva))

        if not movimentos:
            messages.warning(request, "Nenhuma quantidade informada para movimentar.")
            return redirect('ajuste_estoque')

        with transaction.atomic():
            for produto, qtd, obs in movimentos:
                if modo == 'entrada':
                    novo_estoque = produto.quantidade + qtd
                    tipo = 'entrada'
                else:
                    if produto.quantidade - qtd < 0:
                        messages.error(
                            request,
                            f"Saída inválida para '{produto.nome}': estoque insuficiente."
                        )
                        transaction.set_rollback(True)
                        return redirect('ajuste_estoque')
                    novo_estoque = produto.quantidade - qtd
                    tipo = 'saida'

                produto.quantidade = novo_estoque
                produto.save()

                MovimentacaoEstoque.objects.create(
                    produto=produto,
                    tipo=tipo,
                    quantidade=qtd,
                    estoque_final=novo_estoque,
                    observacao=obs  # ✅ usa a observação efetiva (item ou global)
                )

        messages.success(request, "Movimentações salvas com sucesso!")
        return redirect('ajuste_estoque')

    return render(request, 'loja/ajuste_estoque.html', {'produtos': produtos})


@staff_required
def historico_estoque(request):
    movimentacoes = MovimentacaoEstoque.objects.select_related('produto').order_by('-data')
    return render(request, 'loja/historico_estoque.html', {'movimentacoes': movimentacoes})


# FUNÇÃO AUXILIAR SEM DECORATOR
def get_or_create_carrinho(usuario):
    carrinho, criado = Carrinho.objects.get_or_create(usuario=usuario)
    return carrinho


def adicionar_ao_carrinho(request, produto_id):
    produto = get_object_or_404(Produto, id=produto_id)

    if request.user.is_authenticated:
        # 🔒 Usuário logado → Carrinho no banco
        carrinho = get_or_create_carrinho(request.user)
        item, criado = ItemCarrinho.objects.get_or_create(
            carrinho=carrinho,
            produto=produto,
            defaults={'preco_unitario': produto.preco, 'quantidade': 1}
        )
        if not criado:
            item.quantidade += 1
            item.save()
        carrinho.calcular_total()

        # 🔹 Atualiza contador na navbar
        request.session["carrinho_itens"] = sum(i.quantidade for i in carrinho.itemcarrinho_set.all())

    else:
        # 👤 Usuário anônimo → Carrinho na sessão
        carrinho_sessao = request.session.get("carrinho", {})
        if str(produto_id) in carrinho_sessao:
            carrinho_sessao[str(produto_id)]["quantidade"] += 1
        else:
            carrinho_sessao[str(produto_id)] = {
                "nome": produto.nome,
                "preco_unitario": str(produto.preco),
                "quantidade": 1,
                "imagem": produto.imagem.url if produto.imagem else None,
            }
        request.session["carrinho"] = carrinho_sessao

        # 🔹 Atualiza contador na navbar
        request.session["carrinho_itens"] = sum(item["quantidade"] for item in carrinho_sessao.values())

    request.session.modified = True
    messages.success(request, f"'{produto.nome}' foi adicionado ao carrinho.")
    return redirect('ver_carrinho')


def ver_carrinho(request):
    if request.user.is_authenticated:
        # 🔒 Usuário logado → usa carrinho do banco
        carrinho = get_or_create_carrinho(request.user)
        itens = []

        for item in ItemCarrinho.objects.filter(carrinho=carrinho):
            itens.append({
                "id": item.id,
                "nome": item.produto.nome,  # ✅ padroniza com o mesmo nome do anônimo
                "quantidade": item.quantidade,
                "preco_unitario": item.preco_unitario,
                "subtotal": item.subtotal(),
                "imagem": item.produto.imagem.url if item.produto.imagem else None,
            })

        total = carrinho.valor_total
        return render(request, 'loja/carrinho.html', {
            'itens': itens,
            'total': total,
            'sessao': False
        })

    else:
        # 👤 Usuário anônimo → usa carrinho da sessão
        carrinho_sessao = request.session.get("carrinho", {})
        itens = []
        total = Decimal('0.00')

        for produto_id, dados in carrinho_sessao.items():
            subtotal = Decimal(dados["preco_unitario"]) * dados["quantidade"]
            total += subtotal
            itens.append({
                "id": produto_id,
                "nome": dados["nome"],  # ✅ mesma chave que no logado
                "quantidade": dados["quantidade"],
                "preco_unitario": Decimal(dados["preco_unitario"]),
                "subtotal": subtotal,
                "imagem": dados.get("imagem"),
            })

        return render(request, 'loja/carrinho.html', {
            'itens': itens,
            'total': total,
            'sessao': True
        })
        
def remover_do_carrinho(request, item_id):
    if request.user.is_authenticated:
        # 🔒 Usuário logado → remove do banco
        item = get_object_or_404(ItemCarrinho, id=item_id, carrinho__usuario=request.user)
        carrinho = item.carrinho
        item.delete()
        carrinho.calcular_total()

        # 🔹 Atualiza contador na navbar
        request.session["carrinho_itens"] = sum(i.quantidade for i in carrinho.itemcarrinho_set.all())

    else:
        # 👤 Usuário anônimo → remove da sessão
        carrinho_sessao = request.session.get("carrinho", {})
        if str(item_id) in carrinho_sessao:
            del carrinho_sessao[str(item_id)]
            request.session["carrinho"] = carrinho_sessao

        # 🔹 Atualiza contador na navbar
        request.session["carrinho_itens"] = sum(item["quantidade"] for item in carrinho_sessao.values())

    request.session.modified = True
    return redirect('ver_carrinho')

def alterar_quantidade(request, item_id):
    if request.user.is_authenticated:
        # 🔒 Usuário logado → altera no banco
        item = get_object_or_404(ItemCarrinho, id=item_id, carrinho__usuario=request.user)
        if request.method == "POST":
            qtd = int(request.POST.get('quantidade', 1))
            if qtd > 0:
                item.quantidade = qtd
                item.save()
            else:
                item.delete()
            item.carrinho.calcular_total()

            # 🔹 Atualiza contador na navbar
            request.session["carrinho_itens"] = sum(i.quantidade for i in item.carrinho.itemcarrinho_set.all())

    else:
        # 👤 Usuário anônimo → altera na sessão
        carrinho_sessao = request.session.get("carrinho", {})
        if str(item_id) in carrinho_sessao:
            try:
                qtd = int(request.POST.get('quantidade', 1))
            except ValueError:
                qtd = 1

            if qtd > 0:
                carrinho_sessao[str(item_id)]["quantidade"] = qtd
            else:
                del carrinho_sessao[str(item_id)]

            request.session["carrinho"] = carrinho_sessao

        # 🔹 Atualiza contador na navbar
        request.session["carrinho_itens"] = sum(item["quantidade"] for item in carrinho_sessao.values())

    request.session.modified = True
    return redirect('ver_carrinho')

def migrar_carrinho_sessao_para_usuario(request, user):
    carrinho_sessao = request.session.get("carrinho", {})
    if not carrinho_sessao:
        return
    
    carrinho = get_or_create_carrinho(user)

    for produto_id, dados in carrinho_sessao.items():
        try:
            produto = Produto.objects.get(id=produto_id)
        except Produto.DoesNotExist:
            continue  # ignora produtos que não existem mais

        item, criado = ItemCarrinho.objects.get_or_create(
            carrinho=carrinho,
            produto=produto,
            defaults={
                "preco_unitario": produto.preco,
                "quantidade": dados["quantidade"]
            }
        )
        if not criado:
            item.quantidade += dados["quantidade"]
            item.save()

    carrinho.calcular_total()
    # limpa carrinho da sessão
    if "carrinho" in request.session:
        del request.session["carrinho"]
        request.session.modified = True

def adicionar_carrinho(request, produto_id):
    produto = get_object_or_404(Produto, id=produto_id)

    if request.user.is_authenticated:
        # 🔒 Usuário logado → Carrinho no banco
        carrinho, _ = Carrinho.objects.get_or_create(usuario=request.user)
        item, created = ItemCarrinho.objects.get_or_create(
            carrinho=carrinho,
            produto=produto,
            defaults={"quantidade": 1, "preco_unitario": produto.preco}
        )
        if not created:
            item.quantidade += 1
            item.save()

        total_itens = sum(i.quantidade for i in carrinho.itemcarrinho_set.all())
        request.session["carrinho_itens"] = total_itens

    else:
        # 👤 Usuário anônimo → Carrinho na sessão
        carrinho_sessao = request.session.get("carrinho", {})
        if str(produto_id) in carrinho_sessao:
            carrinho_sessao[str(produto_id)]["quantidade"] += 1
        else:
            carrinho_sessao[str(produto_id)] = {
                "nome": produto.nome,
                "preco_unitario": str(produto.preco),
                "quantidade": 1,
                "imagem": produto.imagem.url if produto.imagem else None,
            }
        request.session["carrinho"] = carrinho_sessao

        total_itens = sum(item["quantidade"] for item in carrinho_sessao.values())
        request.session["carrinho_itens"] = total_itens

    request.session.modified = True

    # 🔹 Sempre retorna JSON no AJAX
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"success": True, "total_itens": total_itens})

    return JsonResponse({"success": False})


@login_required
def finalizar_compra(request):
    """Finaliza a compra, cria o pedido com itens congelados (nome, preço e custo)."""
    
    # 1) Busca carrinho
    try:
        carrinho = Carrinho.objects.get(usuario=request.user)
    except Carrinho.DoesNotExist:
        messages.error(request, "Seu carrinho está vazio.")
        return redirect('ver_carrinho')

    itens = carrinho.itemcarrinho_set.all()
    if not itens.exists():
        messages.warning(request, "Seu carrinho está vazio.")
        return redirect('ver_carrinho')

    if request.method == 'POST':
        # 2) Pega dados do form
        nome = request.POST.get("nome", "").strip()
        rua = request.POST.get("rua", "").strip()
        numero = request.POST.get("numero", "").strip()
        bairro = request.POST.get("bairro", "").strip()
        cidade = request.POST.get("cidade", "").strip()
        complemento = request.POST.get("complemento", "").strip()
        referencia = request.POST.get("referencia", "").strip()

        # 3) Validação
        if not all([nome, rua, numero, bairro, cidade]):
            messages.error(request, "Preencha todos os campos obrigatórios.")
            return render(request, 'loja/finalizar_compra.html', {
                'itens': itens,
                'total': carrinho.total(),
                'numero_vendedor': getattr(settings, 'WHATSAPP_NUMBER', '5518981078919'),
            })

        # 4) Monta endereço
        endereco_parts = [f"{rua}, {numero}", f"{bairro} – {cidade}"]
        if complemento:
            endereco_parts.append(f"Complemento: {complemento}")
        if referencia:
            endereco_parts.append(f"Referência: {referencia}")
        endereco_texto = "\n".join(endereco_parts)

        try:
            # 5) Cria pedido
            pedido = Pedido.objects.create(
                cliente=request.user,
                total=Decimal(str(carrinho.total())),
                status='Pendente',
                nome_cliente=nome,
                endereco_entrega=endereco_texto
            )
            
            # 6) Cria itens do pedido (congelando valores)
            for item in itens:
                custo_unit = getattr(item.produto.custo_info, "custo", 0) if item.produto and hasattr(item.produto, "custo_info") else 0

                PedidoItem.objects.create(
                    pedido=pedido,
                    produto=item.produto,  # mantém referência, mas pode ser nulo no futuro
                    nome_produto=item.produto.nome if item.produto else "Produto removido",
                    quantidade=item.quantidade,
                    preco_unitario=item.preco_unitario,
                    custo_unitario=custo_unit
                )

            # 7) Limpa carrinho
            itens.delete()
            carrinho.valor_total = Decimal('0.00')
            carrinho.save()

            request.session["carrinho_itens"] = 0
            request.session.modified = True

        except Exception as e:
            import traceback
            traceback.print_exc()
            messages.error(request, f"Erro ao criar pedido: {str(e)}")
            return render(request, 'loja/finalizar_compra.html', {
                'itens': itens,
                'total': carrinho.total(),
                'numero_vendedor': getattr(settings, 'WHATSAPP_NUMBER', '5518981078919'),
            })

        # 8) Monta WhatsApp
        produtos_texto = []
        for item in pedido.itens.all():
            produtos_texto.append(f"- {item.quantidade}x {item.nome_produto} – R$ {item.subtotal()}")

        mensagem_parts = [
            f"🛒 *Pedido {pedido.numero_pedido} realizado através do site*:",
            "",
            "📦 *Produtos:*",
            *produtos_texto,
            "",
            f"💰 *Total:* R$ {pedido.total}",
            "",
            "📍 *Endereço de entrega:*",
            *endereco_texto.split("\n"),
            "",
            f"🙋 Cliente: {nome}",
            "",
            "Agradeço desde já! 😊",
        ]

        mensagem_final = "\n".join(mensagem_parts)
        numero_vendedor = getattr(settings, 'WHATSAPP_NUMBER', '5518981078919')
        whatsapp_url = f"https://wa.me/{numero_vendedor}?text={quote(mensagem_final)}"

        # 9) Sucesso → página de confirmação
        return render(request, "loja/pedido_confirmado.html", {
            "whatsapp_url": whatsapp_url,
            "pedido_id": pedido.id,
            "nome_cliente": nome,
            "numero_pedido": pedido.numero_pedido,
        })

    # GET
    return render(request, 'loja/finalizar_compra.html', {
        'itens': itens,
        'total': carrinho.total(),
        'numero_vendedor': getattr(settings, 'WHATSAPP_NUMBER', '5518981078919'),
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

    # ❌ Antes: aqui havia lógica de POST para mudar status
    # ✅ Agora: removemos essa lógica,
    # pois o formulário já envia para atualizar_status_pedido

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
        # Se mudou de Pendente para Pago, faz a baixa de estoque
        if novo_status == "Pago" and pedido.status != "Pago":
            for item in pedido.itens.all():
                produto = item.produto
                # Evita estoque negativo
                if produto.quantidade < item.quantidade:
                    messages.error(
                        request,
                        f"Estoque insuficiente para o produto '{produto.nome}'. "
                        f"Disponível: {produto.quantidade}, necessário: {item.quantidade}."
                    )
                    return redirect("detalhes_pedido", pedido_id=pedido.id)

                # Baixa no estoque
                produto.quantidade -= item.quantidade
                produto.save()

                # Registra movimentação
                from .models import MovimentacaoEstoque
                MovimentacaoEstoque.objects.create(
                    produto=produto,
                    tipo="saida",  # usamos "saida" para manter padrão do histórico
                    quantidade=item.quantidade,  # sempre positivo
                    estoque_final=produto.quantidade,
                    observacao=f"Baixa automática por pagamento do pedido {pedido.numero_pedido or pedido.id}"
                )


        pedido.status = novo_status
        pedido.save()
        messages.success(request, f"Status do pedido #{pedido.id} atualizado para '{novo_status}'.")
    else:
        messages.error(request, "Status inválido.")

    return redirect("pedidos")

@staff_required
@require_POST
def atualizar_status_pedidos_lote(request):
    """
    Atualiza o status de múltiplos pedidos selecionados na listagem.
    - Se status for 'Pago', baixa automaticamente do estoque.
    - Se já estava Pago, não baixa de novo.
    """
    from .models import Pedido, MovimentacaoEstoque

    # Pega os IDs dos pedidos selecionados
    pedido_ids = request.POST.getlist("pedidos")
    novo_status = request.POST.get("status")

    if not pedido_ids:
        messages.warning(request, "Nenhum pedido selecionado.")
        return redirect("pedidos")

    if novo_status not in ["Pendente", "Pago", "Cancelado"]:
        messages.error(request, "Status inválido.")
        return redirect("pedidos")

    pedidos = Pedido.objects.filter(id__in=pedido_ids)
    alterados = 0

    for pedido in pedidos:
        # Se o status é Pago e ainda não estava Pago -> baixa estoque
        if novo_status == "Pago" and pedido.status != "Pago":
            for item in pedido.itens.all():
                produto = item.produto
                # Verifica estoque suficiente
                if produto.quantidade < item.quantidade:
                    messages.error(
                        request,
                        f"Estoque insuficiente para o produto '{produto.nome}' "
                        f"no pedido {pedido.numero_pedido or pedido.id}. "
                        f"Disponível: {produto.quantidade}, necessário: {item.quantidade}."
                    )
                    return redirect("pedidos")

                # Atualiza estoque
                produto.quantidade -= item.quantidade
                produto.save()

                # Cria movimentação de saída
                MovimentacaoEstoque.objects.create(
                    produto=produto,
                    tipo="saida",
                    quantidade=item.quantidade,  # sempre positivo
                    estoque_final=produto.quantidade,
                    observacao=f"Baixa automática por pagamento do pedido {pedido.numero_pedido or pedido.id}"
                )

        pedido.status = novo_status
        pedido.save()
        alterados += 1

    messages.success(request, f"{alterados} pedido(s) atualizado(s) para '{novo_status}'.")
    return redirect("pedidos")


# ============================
# ✅ NOVA VIEW: RELATÓRIOS
# ============================
@staff_required  
def relatorios(request):
    pedidos_pagos = Pedido.objects.filter(status='Pago')
    todos_pedidos = Pedido.objects.all()

    mes_labels, mes_values = _agregar_vendas_por_mes(pedidos_pagos)
    dia_labels, dia_values = _agregar_vendas_mes_atual_por_dia(pedidos_pagos)
    status_labels, status_values = _contagem_pedidos_por_status(todos_pedidos)

    context = {
        'mes_labels_json': json.dumps(mes_labels, ensure_ascii=False),
        'mes_values_json': json.dumps(mes_values),
        'dia_labels_json': json.dumps(dia_labels, ensure_ascii=False),
        'dia_values_json': json.dumps(dia_values),
        'status_labels_json': json.dumps(status_labels, ensure_ascii=False),
        'status_values_json': json.dumps(status_values),
        'tabela_mensal': list(zip(mes_labels, mes_values)),
    }
    return render(request, 'loja/relatorios.html', context)

def _agregar_vendas_por_mes(queryset):
    """
    Soma total por mês do ANO ATUAL (1..12), preenchendo zeros onde não houver venda.
    """
    ano = timezone.localdate().year
    labels = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']
    values = [0.0] * 12

    pedidos_ano = queryset.filter(data_criacao__year=ano)
    
    if pedidos_ano.count() == 0:
        return labels, values

    try:
        agregados = (
            pedidos_ano
            .extra(select={'mes_num': "EXTRACT(month FROM data_criacao)"})
            .values('mes_num')
            .annotate(total=Sum('total'))
            .order_by('mes_num')
        )

        for row in agregados:
            mes_num = row['mes_num']
            total = row['total']
            
            if mes_num and 1 <= mes_num <= 12:
                values[int(mes_num) - 1] = float(total) if total else 0.0

    except Exception as e:
        # Fallback: método manual
        for pedido in pedidos_ano:
            mes = pedido.data_criacao.month
            total = float(pedido.total) if pedido.total else 0.0
            values[mes - 1] += total

    return labels, values


def _agregar_vendas_mes_atual_por_dia(queryset):
    """
    Retorna dois arrays: lista de dias (1 a último do mês)
    e valores de vendas por dia (0 nos dias sem venda).
    """
    agora_local = timezone.localtime()
    ano, mes = agora_local.year, agora_local.month

    ultimo_dia_mes = monthrange(ano, mes)[1]
    todos_dias = list(range(1, ultimo_dia_mes + 1))

    # Filtra pedidos do mês atual
    todos_pedidos = queryset.all()
    pedidos_mes = []
    
    for pedido in todos_pedidos:
        data_local = timezone.localtime(pedido.data_criacao)
        if data_local.year == ano and data_local.month == mes:
            pedidos_mes.append(pedido)

    try:
        if len(pedidos_mes) == 0:
            vendas_dict = {}
        else:
            vendas_dict = {}
            for pedido in pedidos_mes:
                data_local = timezone.localtime(pedido.data_criacao)
                dia = data_local.day
                total = float(pedido.total) if pedido.total else 0.0
                if dia not in vendas_dict:
                    vendas_dict[dia] = 0.0
                vendas_dict[dia] += total

    except Exception as e:
        vendas_dict = {}

    labels = [f"{dia:02d}" for dia in todos_dias]
    valores = [vendas_dict.get(dia, 0) for dia in todos_dias]
    
    return labels, valores

def _contagem_pedidos_por_status(queryset):
    """Conta pedidos por status"""
    from django.db.models import Count
    
    status_counts = (
        queryset
        .values('status')
        .annotate(count=Count('status'))
        .order_by('status')
    )
    
    labels = []
    values = []
    
    for item in status_counts:
        labels.append(item['status'])
        values.append(item['count'])
    
    return labels, values


@login_required
def meus_pedidos(request):
    """
    Exibe todos os pedidos feitos pelo usuário logado.
    """
    pedidos = Pedido.objects.filter(cliente=request.user).order_by('-data_criacao')
    return render(request, 'loja/meus_pedidos.html', {'pedidos': pedidos})

@login_required
def detalhes_pedido_cliente(request, pedido_id):
    """
    Mostra os detalhes de um pedido específico para o cliente logado.
    - Garante que o usuário só veja os pedidos dele mesmo.
    """
    pedido = get_object_or_404(Pedido, id=pedido_id, cliente=request.user)
    itens = pedido.itens.all()

    context = {
        "pedido": pedido,
        "itens": itens,
    }
    
    return render(request, "loja/detalhes_pedido_cliente.html", context)

# ============================
# ✅ NOVA VIEW: FESDBACKS
# ============================
@login_required
def adicionar_feedback(request, produto_id):
    produto = get_object_or_404(Produto, id=produto_id)

    if request.method == "POST":
        form = FeedbackForm(request.POST)
        if form.is_valid():
            feedback = form.save(commit=False)
            feedback.usuario = request.user
            feedback.produto = produto
            feedback.save()
            messages.success(request, "Obrigado pelo seu feedback!")
            return redirect("produto_detalhe", produto_id=produto.id)
    else:
        form = FeedbackForm()

    return render(request, "loja/adicionar_feedback.html", {
        "form": form,
        "produto": produto
    })

@staff_required
def listar_feedbacks(request):
    feedbacks = Feedback.objects.select_related("usuario", "produto").order_by("-data_criacao")

    # Filtros
    usuario = request.GET.get("usuario")
    produto = request.GET.get("produto")
    nota = request.GET.get("nota")
    status = request.GET.get("status")
    data_inicio = request.GET.get("data_inicio")
    data_fim = request.GET.get("data_fim")

    if usuario:
        feedbacks = feedbacks.filter(usuario__username__icontains=usuario)
    if produto:
        feedbacks = feedbacks.filter(produto__nome__icontains=produto)
    if nota:
        feedbacks = feedbacks.filter(nota=nota)
    if status == "visivel":
        feedbacks = feedbacks.filter(visivel=True)
    elif status == "oculto":
        feedbacks = feedbacks.filter(visivel=False)
    if data_inicio:
        feedbacks = feedbacks.filter(data_criacao__date__gte=data_inicio)
    if data_fim:
        feedbacks = feedbacks.filter(data_criacao__date__lte=data_fim)

    return render(request, "loja/listar_feedbacks.html", {"feedbacks": feedbacks})


@staff_required
def detalhes_feedback(request, feedback_id):
    feedback = get_object_or_404(Feedback, id=feedback_id)

    if request.method == "POST":
        # Atualiza visibilidade
        novo_status = request.POST.get("visivel")
        feedback.visivel = True if novo_status == "on" else False
        feedback.save()
        messages.success(request, "Feedback atualizado com sucesso.")
        return redirect("listar_feedbacks")

    return render(request, "loja/detalhes_feedback.html", {"feedback": feedback})

@staff_required
@require_POST
def atualizar_feedbacks_lote(request):
    feedback_ids = request.POST.getlist("feedbacks")
    visibilidade = request.POST.get("visibilidade")

    if not feedback_ids:
        messages.warning(request, "Nenhum feedback selecionado.")
        return redirect("listar_feedbacks")

    feedbacks = Feedback.objects.filter(id__in=feedback_ids)

    if visibilidade == "visivel":
        feedbacks.update(visivel=True)
        messages.success(request, f"{feedbacks.count()} feedback(s) marcados como visíveis.")
    elif visibilidade == "oculto":
        feedbacks.update(visivel=False)
        messages.success(request, f"{feedbacks.count()} feedback(s) marcados como ocultos.")
    else:
        messages.error(request, "Ação inválida.")

    return redirect("listar_feedbacks")
