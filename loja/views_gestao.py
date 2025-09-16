from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Sum
from django.utils.timezone import localtime
from django.db import models
from .models import Produto, CustoProduto, Pedido, PedidoItem, Despesa, Produto, MovimentacaoEstoque
from .forms import DespesaForm
from dateutil.relativedelta import relativedelta
from django.shortcuts import render, redirect, get_object_or_404

# 🔹 Apenas a regra de admin permanece
def admin_required(user):
    return user.is_staff or user.is_superuser

# 🔹 Página inicial da Gestão
@login_required
@user_passes_test(admin_required)
def gestao_index(request):
    return render(request, "loja/gestao/index.html")

def admin_required(user):
    return user.is_staff or user.is_superuser

@login_required
@user_passes_test(admin_required)
def gestao_estoque(request):
    produtos = Produto.objects.all().order_by("nome")
    modo_edicao = request.GET.get("modo") == "editar"

    # 🔍 --- BUSCA POR NOME ---
    q = request.GET.get("q")
    if q:
        produtos = produtos.filter(nome__icontains=q)

    # 🔽 --- FILTROS DE ESTOQUE ---
    filtro = request.GET.get("filtro")
    if filtro == "baixo":
        produtos = produtos.filter(quantidade__lt=models.F("minimo_estoque"))
    elif filtro == "medio":
        produtos = produtos.filter(
            quantidade__gte=models.F("minimo_estoque"),
            quantidade__lte=models.F("ideal_estoque")
        )
    elif filtro == "alto":
        produtos = produtos.filter(quantidade__gt=models.F("ideal_estoque"))

    # 🔄 --- ATUALIZAÇÃO DE LIMITES ---
    if request.method == "POST":
        atualizados = []
        for produto in produtos:
            minimo = request.POST.get(f"minimo_{produto.id}")
            ideal = request.POST.get(f"ideal_{produto.id}")
            if minimo and ideal:
                produto.minimo_estoque = int(minimo)
                produto.ideal_estoque = int(ideal)
                produto.save()

                ultima_mov_produto = MovimentacaoEstoque.objects.filter(produto=produto).order_by("-data").first()
                data_mov = localtime(ultima_mov_produto.data).strftime("%d/%m/%Y %H:%M") if ultima_mov_produto else "-"

                atualizados.append({
                    "id": produto.id,
                    "minimo": produto.minimo_estoque,
                    "ideal": produto.ideal_estoque,
                    "ultima_atualizacao": data_mov,
                })

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": True, "atualizados": atualizados})

        messages.success(request, "Limites atualizados com sucesso!")
        return redirect("gestao_estoque")

    # 📊 --- CARDS ---
    total_produtos = produtos.count()
    produtos_baixo_estoque = produtos.filter(quantidade__lt=models.F("minimo_estoque")).count()
    ultima_mov = MovimentacaoEstoque.objects.order_by("-data").first()
    ultima_movimentacao = localtime(ultima_mov.data).strftime("%d/%m/%Y %H:%M") if ultima_mov else "-"

    # 📋 --- TABELA DE PRODUTOS ---
    tabela_produtos = []
    for produto in produtos:
        minimo = produto.minimo_estoque or 0
        ideal = produto.ideal_estoque or 1
        qtd = produto.quantidade

        # Percentual baseado no ideal
        percentual = int((qtd / ideal) * 100) if ideal > 0 else 0
        if percentual > 100:
            percentual = 100  # barra nunca passa de 100%

        # Regras de cor
        if qtd < minimo:
            cor = "bg-danger"  # vermelho
        elif qtd <= ideal:
            cor = "bg-success"  # verde
        else:
            cor = "bg-warning text-dark"  # amarelo

        ultima_mov_produto = MovimentacaoEstoque.objects.filter(produto=produto).order_by("-data").first()
        data_mov = localtime(ultima_mov_produto.data).strftime("%d/%m/%Y %H:%M") if ultima_mov_produto else "-"

        tabela_produtos.append({
            "id": produto.id,
            "nome": produto.nome,
            "quantidade": qtd,
            "percentual": percentual,
            "cor": cor,
            "ultima_atualizacao": data_mov,
            "minimo": produto.minimo_estoque,
            "ideal": produto.ideal_estoque,
        })

    # 🔹 Retorno JSON quando é requisição AJAX (busca/filtro dinâmico)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"produtos": tabela_produtos})

    context = {
        "modo_edicao": modo_edicao,
        "total_produtos": total_produtos,
        "produtos_baixo_estoque": produtos_baixo_estoque,
        "ultima_movimentacao": ultima_movimentacao,
        "tabela_produtos": tabela_produtos,
    }
    return render(request, "loja/gestao/estoque.html", context)

@login_required
@user_passes_test(admin_required)
def financeiro_produtos(request):
    produtos = Produto.objects.all().order_by("nome")

    # 🔹 Modo edição de custos
    if request.method == "POST":
        for produto in produtos:
            custo_valor = request.POST.get(f"custo_{produto.id}")
            if custo_valor is not None:
                custo_valor = float(custo_valor) if custo_valor else 0
                custo_obj, _ = CustoProduto.objects.get_or_create(produto=produto)
                custo_obj.custo = custo_valor
                custo_obj.save()
        messages.success(request, "Custos atualizados com sucesso!")
        return redirect("financeiro_produtos")

    # 🔹 Montagem dos dados
    produtos_data = []
    for p in produtos:
        custo = getattr(p.custo_info, "custo", 0) if hasattr(p, "custo_info") else 0
        preco = p.preco
        lucro_unitario = preco - custo
        margem = (lucro_unitario / custo * 100) if custo > 0 else 0

        produtos_data.append({
            "id": p.id,
            "nome": p.nome,
            "custo": float(custo),
            "preco": float(preco),
            "lucro_unitario": float(lucro_unitario),
            "margem": round(margem, 2),
        })

    context = {"produtos_data": produtos_data}
    return render(request, "loja/gestao/financeiro_produtos.html", context)

@login_required
@user_passes_test(admin_required)
def financeiro_pedidos(request):
    # 🔹 Pega pedidos mais recentes primeiro
    pedidos = Pedido.objects.filter(status="Pago").select_related("cliente").order_by("-data_criacao")

    pedidos_data = []
    for p in pedidos:
        receita = p.total or 0

        # 🔹 Calcula custo do pedido
        itens = PedidoItem.objects.filter(pedido=p).select_related("produto")
        custo_total = 0
        for item in itens:
            if hasattr(item.produto, "custo_info"):
                custo_produto = item.produto.custo_info.custo
            else:
                custo_produto = 0
            custo_total += item.quantidade * custo_produto

        lucro = receita - custo_total

        pedidos_data.append({
            "numero": p.numero_pedido or p.id,
            "cliente": p.cliente.username,
            "data": p.data_criacao.strftime("%d/%m/%Y"),
            "receita": float(receita),
            "custo": float(custo_total),
            "lucro": float(lucro),
        })

    context = {"pedidos_data": pedidos_data}
    return render(request, "loja/gestao/financeiro_pedidos.html", context)

@login_required
@user_passes_test(admin_required)
def financeiro_resumo(request):
    pedidos = Pedido.objects.filter(status="Pago")

    # Receita total
    receita_total = pedidos.aggregate(total=Sum("total"))["total"] or 0

    # Custo total
    custo_total = 0
    itens = PedidoItem.objects.filter(pedido__in=pedidos).select_related("produto")
    for item in itens:
        if hasattr(item.produto, "custo_info"):
            custo_produto = item.produto.custo_info.custo
        else:
            custo_produto = 0
        custo_total += item.quantidade * custo_produto

    # Lucro líquido
    lucro_liquido = receita_total - custo_total

    context = {
        "receita_total": receita_total,
        "custo_total": custo_total,
        "lucro_liquido": lucro_liquido,
    }
    return render(request, "loja/gestao/financeiro_resumo.html", context)

@login_required
@user_passes_test(admin_required)
def gestao_despesas(request):
    despesas = Despesa.objects.all().order_by("-data")  # mais recentes primeiro
    context = {
        "despesas": despesas,
    }
    return render(request, "loja/gestao/gestao_despesas.html", context)

@login_required
@user_passes_test(admin_required)
def criar_despesa(request):
    if request.method == "POST":
        form = DespesaForm(request.POST)
        if form.is_valid():
            despesa = form.save(commit=False)

            # número de parcelas
            num_parcelas = despesa.parcelas if despesa.parcelas > 0 else 1
            data_base = despesa.data

            for i in range(num_parcelas):
                nova_despesa = Despesa.objects.create(
                    categoria=despesa.categoria,
                    tipo=despesa.tipo,
                    valor=despesa.valor,
                    data=data_base + relativedelta(months=i),
                    descricao=despesa.descricao,
                    fornecedor=despesa.fornecedor,
                    parcelas=1  # cada registro individual representa 1 parcela
                )

            messages.success(request, f"{num_parcelas} despesa(s) cadastrada(s) com sucesso!")
            return redirect("gestao_despesas")
    else:
        form = DespesaForm()

    return render(request, "loja/gestao/criar_despesa.html", {"form": form})

@login_required
@user_passes_test(admin_required)
def editar_despesa(request, pk):
    despesa = get_object_or_404(Despesa, pk=pk)
    if request.method == "POST":
        form = DespesaForm(request.POST, instance=despesa)
        if form.is_valid():
            form.save()
            messages.success(request, "Despesa atualizada com sucesso!")
            return redirect("gestao_despesas")
    else:
        form = DespesaForm(instance=despesa)

    return render(request, "loja/gestao/editar_despesa.html", {"form": form, "despesa": despesa})


@login_required
@user_passes_test(admin_required)
def excluir_despesa(request, pk):
    despesa = get_object_or_404(Despesa, pk=pk)
    if request.method == "POST":
        despesa.delete()
        messages.success(request, "Despesa excluída com sucesso!")
        return redirect("gestao_despesas")

    return render(request, "loja/gestao/excluir_despesa.html", {"despesa": despesa})

def relatorio_avancado(request):
    """
    Página de relatórios avançados com filtros.
    Por enquanto está funcionando apenas para Produtos.
    """
    produtos = Produto.objects.all()

    # Captura filtros da query string (GET)
    nome = request.GET.get("nome")
    preco_min = request.GET.get("preco_min")
    preco_max = request.GET.get("preco_max")
    qtd_min = request.GET.get("qtd_min")
    qtd_max = request.GET.get("qtd_max")

    # Aplica filtros dinamicamente
    if nome:
        produtos = produtos.filter(nome__icontains=nome)
    if preco_min:
        produtos = produtos.filter(preco__gte=preco_min)
    if preco_max:
        produtos = produtos.filter(preco__lte=preco_max)
    if qtd_min:
        produtos = produtos.filter(quantidade__gte=qtd_min)
    if qtd_max:
        produtos = produtos.filter(quantidade__lte=qtd_max)

    context = {
        "produtos": produtos,
    }
    return render(request, "loja/gestao/relatorio_avancado.html", context)