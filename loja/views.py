from django.shortcuts import render, redirect, get_object_or_404
from .models import Produto, Carrinho, ItemCarrinho, Pedido, PedidoItem
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login, authenticate, logout
from .forms import RegistroForm
from django.views.decorators.http import require_POST
from .decorators import staff_required
from django.contrib.auth.models import User
from django.contrib import messages
from .models import EntradaEstoque
from .models import MovimentacaoEstoque
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db.models import Q
from django.db.models import Sum, Count  # ✅ Count para agregações por status
from django.db import transaction
from urllib.parse import quote
from decimal import Decimal
from django.utils import timezone
from django.db.models.functions import ExtractMonth, ExtractDay 
from calendar import monthrange
from django.db.models.functions import Coalesce
from django.db.models import Sum, Count, DecimalField, Value
from django.db.models.functions import ExtractMonth, ExtractDay, Coalesce


# 👇 extras para serializar dados pro Chart.js
import json
from calendar import month_name
from calendar import monthrange


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
        # Passa o usuário autenticado para o form conforme sua regra
        form = RegistroForm(request.POST, user=request.user)
        if form.is_valid():
            user = form.save()
            login(request, user)  # Faz login automaticamente após o cadastro
            return redirect('home')
    else:
        form = RegistroForm(user=request.user)
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
    Dashboard administrativo com mini-gráfico do mês.
    Mostra vendas pagas no mês atual.
    """
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
    ano = agora.year
    mes = agora.month
    inicio_mes = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Total de vendas do mês (somente pedidos pagos)
    vendas_mes = (
        Pedido.objects
        .filter(status='Pago', data_criacao__gte=inicio_mes)
        .aggregate(total=Sum('total'))
        .get('total') or 0
    )

    # Filtra apenas pedidos pagos do mês atual
    pedidos_pagos = Pedido.objects.filter(
        status='Pago',
        data_criacao__year=ano,
        data_criacao__month=mes
    )

    # Gera os dados para o mini gráfico
    mini_labels, mini_values = _agregar_vendas_mes_atual_por_dia(pedidos_pagos)

    ctx = {
        'form': form,
        'vendas_mes': vendas_mes,
        'mini_mes_labels_json': json.dumps(mini_labels, ensure_ascii=False),
        'mini_mes_values_json': json.dumps(mini_values),
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
    """
    Fluxo:
    - GET: mostra o formulário de entrega.
    - POST: valida dados, cria Pedido e PedidoItem, limpa carrinho e exibe
            a página de confirmação que abrirá o WhatsApp em nova aba.
    """
    # 1) Busca carrinho do usuário
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
        # 2) Captura/valida campos do formulário
        nome = (request.POST.get("nome") or "").strip()
        rua = (request.POST.get("rua") or "").strip()
        numero = (request.POST.get("numero") or "").strip()
        bairro = (request.POST.get("bairro") or "").strip()
        cidade = (request.POST.get("cidade") or "").strip()
        complemento = (request.POST.get("complemento") or "").strip()
        referencia = (request.POST.get("referencia") or "").strip()

        if not all([nome, rua, numero, bairro, cidade]):
            messages.error(request, "Por favor, preencha todos os campos obrigatórios de entrega.")
            return render(request, 'loja/finalizar_compra.html', {
                'itens': itens,
                'total': carrinho.total(),
                'numero_vendedor': getattr(settings, 'WHATSAPP_NUMBER', '5599999999999'),
                'form': {  # mantém valores digitados
                    'nome': nome, 'rua': rua, 'numero': numero, 'bairro': bairro,
                    'cidade': cidade, 'complemento': complemento, 'referencia': referencia
                }
            })

        # 3) Monta o endereço em texto único para salvar no Pedido
        linhas_endereco = [f"{rua}, {numero}", f"{bairro} – {cidade}"]
        if complemento:
            linhas_endereco.append(f"Complemento: {complemento}")
        if referencia:
            linhas_endereco.append(f"Referência: {referencia}")
        endereco_texto = "\n".join(linhas_endereco)

        # 4) Cria Pedido + Itens de forma atômica e limpa o carrinho
        with transaction.atomic():
            pedido = Pedido.objects.create(
                cliente=request.user,
                total=Decimal(carrinho.total()),  # congela o total no momento do pedido
                status='Pendente',
                nome_cliente=nome,
                endereco_entrega=endereco_texto,
                observacao=""
            )

            for item in itens:
                PedidoItem.objects.create(
                    pedido=pedido,
                    produto=item.produto,
                    quantidade=item.quantidade,
                    preco_unitario=item.preco_unitario
                )

            itens.delete()
            carrinho.valor_total = Decimal('0.00')
            carrinho.save()

        # 5) Monta a mensagem do WhatsApp (texto puro, com quebras de linha)
        linhas = [
            "🛒 *Pedido realizado através do site*:",
            "",
            "📦 *Produtos:*",
        ]
        for item in pedido.itens.all():
            linhas.append(f"- {item.quantidade}x {item.produto.nome} – R$ {item.subtotal()}")

        linhas += [
            "",
            f"💰 *Total:* R$ {pedido.total}",
            "",
            "📍 *Endereço de entrega:*",
            *endereco_texto.split("\n"),
            "",
            f"🙋 Cliente: {nome}",
            "",
            "Agradeço desde já e fico no aguardo da confirmação 😊",
        ]

        mensagem_final = "\n".join(linhas)
        numero_vendedor = getattr(settings, 'WHATSAPP_NUMBER', '5599999999999')
        whatsapp_url = f"https://wa.me/{numero_vendedor}?text={quote(mensagem_final)}"

        # 👉 Em vez de redirecionar, renderiza a página de confirmação
        return render(request, "loja/pedido_confirmado.html", {
            "whatsapp_url": whatsapp_url,
            "pedido_id": pedido.id,
            "nome_cliente": nome,
        })

    # GET — Renderiza a página de finalização
    return render(request, 'loja/finalizar_compra.html', {
        'itens': itens,
        'total': carrinho.total(),
        'numero_vendedor': getattr(settings, 'WHATSAPP_NUMBER', '5599999999999'),
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

    # Debug: imprimir valores para verificar
    print(f"DEBUG - Pedidos pagos: {pedidos_pagos.count()}")
    print(f"DEBUG - Mes values: {mes_values}")

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

    # Debug: verificar se há pedidos no ano atual
    pedidos_ano = queryset.filter(data_criacao__year=ano)
    print(f"DEBUG - Pedidos no ano {ano}: {pedidos_ano.count()}")
    
    if pedidos_ano.count() == 0:
        print(f"DEBUG - Nenhum pedido encontrado no ano {ano}")
        return labels, values

    # Verificar alguns pedidos para debug
    for p in pedidos_ano[:3]:
        print(f"DEBUG - Pedido {p.id}: total={p.total}, data={p.data_criacao}")

    try:
        # Solução 1: Usar TruncMonth para lidar melhor com timezone
        from django.db.models import DateTimeField
        from django.db.models.functions import TruncMonth, Extract
        
        # Converter para timezone local antes de extrair o mês
        agregados = (
            pedidos_ano
            .extra(select={'mes_num': "EXTRACT(month FROM data_criacao)"})
            .values('mes_num')
            .annotate(total=Sum('total'))
            .order_by('mes_num')
        )

        print(f"DEBUG - Agregados query result: {list(agregados)}")

        for row in agregados:
            mes_num = row['mes_num']
            total = row['total']
            print(f"DEBUG - Mês {mes_num}: {total}")
            
            if mes_num and 1 <= mes_num <= 12:
                values[int(mes_num) - 1] = float(total) if total else 0.0

    except Exception as e:
        print(f"DEBUG - Erro na agregação: {e}")
        
        # Fallback: método manual se a query não funcionar
        print("DEBUG - Tentando método manual...")
        for pedido in pedidos_ano:
            mes = pedido.data_criacao.month
            total = float(pedido.total) if pedido.total else 0.0
            values[mes - 1] += total
            print(f"DEBUG - Manual: Pedido {pedido.id} mês {mes} = R$ {total}")

    print(f"DEBUG - Values final: {values}")
    return labels, values


def _agregar_vendas_mes_atual_por_dia(queryset):
    """
    Retorna dois arrays: lista de dias (1 a último do mês)
    e valores de vendas por dia (0 nos dias sem venda).
    """
    # Usar timezone.localtime() para converter para timezone local configurado no Django
    agora_local = timezone.localtime()
    ano, mes = agora_local.year, agora_local.month
    
    print(f"DEBUG - Data atual local: {agora_local}")
    print(f"DEBUG - Buscando pedidos para {mes}/{ano}")

    ultimo_dia_mes = monthrange(ano, mes)[1]
    todos_dias = list(range(1, ultimo_dia_mes + 1))

    # MUDANÇA: não filtrar por ano no Django, buscar todos e filtrar em Python
    todos_pedidos = queryset.all()
    pedidos_mes = []
    
    for pedido in todos_pedidos:
        data_local = timezone.localtime(pedido.data_criacao)
        if data_local.year == ano and data_local.month == mes:
            pedidos_mes.append(pedido)
    
    print(f"DEBUG - Todos pedidos: {todos_pedidos.count()}")
    print(f"DEBUG - Pedidos filtrados para {mes}/{ano} (local): {len(pedidos_mes)}")
    
    for p in pedidos_mes:
        data_local = timezone.localtime(p.data_criacao)
        print(f"DEBUG - Pedido mês atual: {p.id}, dia {data_local.day} (local), total {p.total}")

    try:
        if len(pedidos_mes) == 0:
            print("DEBUG - Nenhum pedido no mês atual, retornando zeros")
            vendas_dict = {}
        else:
            # Método manual usando timezone local
            vendas_dict = {}
            for pedido in pedidos_mes:
                data_local = timezone.localtime(pedido.data_criacao)
                dia = data_local.day
                total = float(pedido.total) if pedido.total else 0.0
                if dia not in vendas_dict:
                    vendas_dict[dia] = 0.0
                vendas_dict[dia] += total
                print(f"DEBUG - Somando: dia {dia} (local) += {total} = {vendas_dict[dia]}")

    except Exception as e:
        print(f"DEBUG - Erro nas vendas por dia: {e}")
        vendas_dict = {}

    labels = [f"{dia:02d}" for dia in todos_dias]
    valores = [vendas_dict.get(dia, 0) for dia in todos_dias]
    
    print(f"DEBUG - Valores finais por dia: {dict(zip(labels, valores))}")
    
    return labels, valores


def _contagem_pedidos_por_status(queryset):
    """
    Conta pedidos por status.
    """
    try:
        agregados = queryset.values('status').annotate(qtd=Count('id')).order_by('status')
        labels = [row['status'] or 'Indefinido' for row in agregados]
        values = [row['qtd'] for row in agregados]
    except Exception as e:
        print(f"DEBUG - Erro na contagem por status: {e}")
        labels = ['Sem dados']
        values = [0]
    
    return labels, values

@staff_required
def dashboard(request):
    from calendar import monthrange
    import json
    from django.utils import timezone
    from django.db.models import Sum
    
    # Dados para o mini gráfico do mês atual
    pedidos_pagos = Pedido.objects.filter(status='Pago')
    
    # Calcular vendas do mês atual
    agora_local = timezone.localtime()
    ano_atual, mes_atual = agora_local.year, agora_local.month
    
    print(f"DEBUG DASHBOARD - Mês atual: {mes_atual:02d}/{ano_atual}")
    
    # Gerar dados dia a dia do mês atual
    ultimo_dia_mes = monthrange(ano_atual, mes_atual)[1]
    todos_dias = list(range(1, ultimo_dia_mes + 1))
    
    # Filtrar pedidos pagos do mês atual
    pedidos_mes_atual = []
    for pedido in pedidos_pagos.all():
        data_local = timezone.localtime(pedido.data_criacao)
        if data_local.year == ano_atual and data_local.month == mes_atual:
            pedidos_mes_atual.append((pedido, data_local))
    
    print(f"DEBUG DASHBOARD - Pedidos pagos no mês atual: {len(pedidos_mes_atual)}")
    
    # Agrupar vendas por dia
    vendas_por_dia = {}
    for pedido, data_local in pedidos_mes_atual:
        dia = data_local.day
        total = float(pedido.total) if pedido.total else 0.0
        
        if dia not in vendas_por_dia:
            vendas_por_dia[dia] = 0.0
        vendas_por_dia[dia] += total
    
    # Preparar dados para o gráfico
    mini_labels = [f"{dia:02d}" for dia in todos_dias]
    mini_values = [vendas_por_dia.get(dia, 0) for dia in todos_dias]
    
    # Calcular total de vendas do mês
    vendas_mes = sum(mini_values)
    
    print(f"DEBUG DASHBOARD - Total vendas mês: R$ {vendas_mes:.2f}")
    print(f"DEBUG DASHBOARD - Dias com vendas: {[dia for dia, valor in zip(todos_dias, mini_values) if valor > 0]}")
    
    context = {
        'mini_mes_labels_json': json.dumps(mini_labels, ensure_ascii=False),
        'mini_mes_values_json': json.dumps(mini_values),
        'vendas_mes': vendas_mes,
        # outros dados que você já tinha no context...
    }
    
    return render(request, 'loja/dashboard.html', context)