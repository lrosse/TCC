from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Sum
from django.utils.timezone import localtime
from django.db import models
from .models import Produto, CustoProduto, Pedido, PedidoItem, Despesa, Produto, MovimentacaoEstoque,LancamentoFinanceiro, Feedback
from .forms import DespesaForm
from dateutil.relativedelta import relativedelta
import weasyprint
from django.http import HttpResponse
from django.template.loader import render_to_string

# 🔹 Apenas a regra de admin permanece
def admin_required(user):
    return user.is_staff or user.is_superuser

# 🔹 Página inicial da Gestão
@login_required
@user_passes_test(admin_required)
def gestao_index(request):
    return render(request, "loja/gestao/index.html")

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
    # Recebe datas do filtro GET ou usa padrão
    data_inicio = request.GET.get("data_inicio") or "2025-09-01"
    data_fim = request.GET.get("data_fim") or "2025-09-30"

    pedidos = Pedido.objects.filter(
        status="Pago",
        data_criacao__gte=data_inicio,
        data_criacao__lte=data_fim
    )
    despesas_fixas = Despesa.objects.filter(
        tipo="Fixo",
        data__gte=data_inicio,
        data__lte=data_fim
    )
    despesas_variaveis = Despesa.objects.filter(
        tipo="Variável",
        data__gte=data_inicio,
        data__lte=data_fim
    )

    # Receita total
    receita_total = pedidos.aggregate(total=Sum("total"))["total"] or 0

    # Custo total (baseado nos custos cadastrados dos produtos)
    custo_total = 0
    itens = PedidoItem.objects.filter(pedido__in=pedidos).select_related("produto")
    for item in itens:
        custo_produto = getattr(item.produto.custo_info, "custo", 0) if hasattr(item.produto, "custo_info") else 0
        custo_total += item.quantidade * custo_produto

    # Despesas
    despesas_fixas_valor = despesas_fixas.aggregate(total=Sum("valor"))["total"] or 0
    despesas_variaveis_valor = despesas_variaveis.aggregate(total=Sum("valor"))["total"] or 0

    # Lucro líquido final = Receita - Custos - Despesas
    lucro_liquido = receita_total - custo_total - despesas_fixas_valor - despesas_variaveis_valor

    context = {
        "receita_total": receita_total,
        "custo_total": custo_total,
        "lucro_liquido": lucro_liquido,
        "despesas_fixas": despesas_fixas_valor,
        "despesas_variaveis": despesas_variaveis_valor,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "mes": None,
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
    tipo = request.GET.get("tipo")  # produtos, pedidos, estoque, financeiro, feedbacks

    context = {"tipo": tipo}

    # -----------------
    # PRODUTOS
    # -----------------
    if tipo == "produtos":
        produtos = Produto.objects.all()

        if nome := request.GET.get("nome"):
            produtos = produtos.filter(nome__icontains=nome)

        if preco_min := request.GET.get("preco_min"):
            produtos = produtos.filter(preco__gte=preco_min)
        if preco_max := request.GET.get("preco_max"):
            produtos = produtos.filter(preco__lte=preco_max)

        if qtd_min := request.GET.get("qtd_min"):
            produtos = produtos.filter(quantidade__gte=qtd_min)
        if qtd_max := request.GET.get("qtd_max"):
            produtos = produtos.filter(quantidade__lte=qtd_max)

        if status := request.GET.get("status_estoque"):
            if status == "minimo":
                produtos = produtos.filter(quantidade__lte=models.F("minimo_estoque"))
            elif status == "ideal":
                produtos = produtos.filter(
                    quantidade__gt=models.F("minimo_estoque"),
                    quantidade__lte=models.F("ideal_estoque")
                )
            elif status == "bom":
                produtos = produtos.filter(quantidade__gt=models.F("ideal_estoque"))

        if ordenar := request.GET.get("ordenar_por"):
            if ordenar == "nome":
                produtos = produtos.order_by("nome")
            elif ordenar == "preco":
                produtos = produtos.order_by("preco")
            elif ordenar == "quantidade":
                produtos = produtos.order_by("quantidade")
            elif ordenar == "recente":
                produtos = produtos.order_by("-id")

        context["produtos"] = produtos

    # -----------------
    # PEDIDOS
    # -----------------
    elif tipo == "pedidos":
        pedidos = Pedido.objects.all()

        if numero := request.GET.get("numero"):
            pedidos = pedidos.filter(numero_pedido__icontains=numero)

        if cliente := request.GET.get("cliente"):
            pedidos = pedidos.filter(cliente__username__icontains=cliente)

        if status := request.GET.get("status"):
            pedidos = pedidos.filter(status=status)

        if valor_min := request.GET.get("valor_min"):
            pedidos = pedidos.filter(total__gte=valor_min)
        if valor_max := request.GET.get("valor_max"):
            pedidos = pedidos.filter(total__lte=valor_max)

        if data_inicio := request.GET.get("data_inicio"):
            pedidos = pedidos.filter(data_criacao__gte=parse_date(data_inicio))
        if data_fim := request.GET.get("data_fim"):
            pedidos = pedidos.filter(data_criacao__lte=parse_date(data_fim))

        context["pedidos"] = pedidos

    # -----------------
    # ESTOQUE
    # -----------------
    elif tipo == "estoque":
        movs = MovimentacaoEstoque.objects.select_related("produto").all()

        if produto := request.GET.get("produto"):
            movs = movs.filter(produto__nome__icontains=produto)

        if tipo_mov := request.GET.get("tipo"):
            movs = movs.filter(tipo=tipo_mov)

        if qtd_min := request.GET.get("qtd_min"):
            movs = movs.filter(quantidade__gte=qtd_min)
        if qtd_max := request.GET.get("qtd_max"):
            movs = movs.filter(quantidade__lte=qtd_max)

        if data_inicio := request.GET.get("data_inicio"):
            movs = movs.filter(data__gte=parse_date(data_inicio))
        if data_fim := request.GET.get("data_fim"):
            movs = movs.filter(data__lte=parse_date(data_fim))

        context["movs"] = movs

    # -----------------
    # FINANCEIRO
    # -----------------
    elif tipo == "financeiro":
        lancamentos = LancamentoFinanceiro.objects.all()

        if tipo_l := request.GET.get("tipo_lancamento"):
            lancamentos = lancamentos.filter(tipo=tipo_l)

        if categoria := request.GET.get("categoria"):
            lancamentos = lancamentos.filter(categoria__icontains=categoria)

        if valor_min := request.GET.get("valor_min"):
            lancamentos = lancamentos.filter(valor__gte=valor_min)
        if valor_max := request.GET.get("valor_max"):
            lancamentos = lancamentos.filter(valor__lte=valor_max)

        if data_inicio := request.GET.get("data_inicio"):
            lancamentos = lancamentos.filter(data__gte=parse_date(data_inicio))
        if data_fim := request.GET.get("data_fim"):
            lancamentos = lancamentos.filter(data__lte=parse_date(data_fim))

        context["lancamentos"] = lancamentos

    # -----------------
    # FEEDBACKS
    # -----------------
    elif tipo == "feedbacks":
        feedbacks = Feedback.objects.select_related("usuario", "produto").all()

        if produto := request.GET.get("produto"):
            feedbacks = feedbacks.filter(produto__nome__icontains=produto)

        if usuario := request.GET.get("usuario"):
            feedbacks = feedbacks.filter(usuario__username__icontains=usuario)

        if nota := request.GET.get("nota"):
            feedbacks = feedbacks.filter(nota=nota)

        if visivel := request.GET.get("visivel"):
            if visivel in ["True", "False"]:
                feedbacks = feedbacks.filter(visivel=(visivel == "True"))

        context["feedbacks"] = feedbacks

    return render(request, "loja/gestao/relatorio_avancado.html", context)

@login_required
@user_passes_test(admin_required)
def relatorio_produtos(request):
    """
    Relatório de Produtos – lista com filtros por nome, preço, quantidade e status de estoque.
    """
    produtos = Produto.objects.all()

    # Filtros
    nome = request.GET.get("nome")
    preco_min = request.GET.get("preco_min")
    preco_max = request.GET.get("preco_max")
    qtd_min = request.GET.get("qtd_min")
    qtd_max = request.GET.get("qtd_max")
    status_estoque = request.GET.get("status_estoque")
    ordenar_por = request.GET.get("ordenar_por")

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

    if status_estoque == "minimo":
        produtos = produtos.filter(quantidade__lte=models.F("minimo_estoque"))
    elif status_estoque == "ideal":
        produtos = produtos.filter(
            quantidade__gt=models.F("minimo_estoque"),
            quantidade__lte=models.F("ideal_estoque"),
        )
    elif status_estoque == "bom":
        produtos = produtos.filter(quantidade__gt=models.F("ideal_estoque"))

    # Ordenação
    if ordenar_por == "nome":
        produtos = produtos.order_by("nome")
    elif ordenar_por == "preco":
        produtos = produtos.order_by("preco")
    elif ordenar_por == "quantidade":
        produtos = produtos.order_by("quantidade")
    elif ordenar_por == "recente":
        produtos = produtos.order_by("-id")

    context = {"produtos": produtos}
    return render(request, "loja/gestao/relatorio_produtos.html", context)

@login_required
@user_passes_test(admin_required)
def relatorio_produtos_pdf(request):
    """
    Exporta o Relatório de Produtos para PDF, aplicando os mesmos filtros da tela.
    """
    produtos = Produto.objects.all()

    # 🔹 Reaproveita a lógica dos filtros (igual a relatorio_produtos)
    nome = request.GET.get("nome")
    preco_min = request.GET.get("preco_min")
    preco_max = request.GET.get("preco_max")
    qtd_min = request.GET.get("qtd_min")
    qtd_max = request.GET.get("qtd_max")
    status_estoque = request.GET.get("status_estoque")
    ordenar_por = request.GET.get("ordenar_por")

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

    if status_estoque == "minimo":
        produtos = produtos.filter(quantidade__lte=models.F("minimo_estoque"))
    elif status_estoque == "ideal":
        produtos = produtos.filter(
            quantidade__gt=models.F("minimo_estoque"),
            quantidade__lte=models.F("ideal_estoque"),
        )
    elif status_estoque == "bom":
        produtos = produtos.filter(quantidade__gt=models.F("ideal_estoque"))

    if ordenar_por == "nome":
        produtos = produtos.order_by("nome")
    elif ordenar_por == "preco":
        produtos = produtos.order_by("preco")
    elif ordenar_por == "quantidade":
        produtos = produtos.order_by("quantidade")
    elif ordenar_por == "recente":
        produtos = produtos.order_by("-id")

    # 🔹 Renderiza o template PDF
    html_string = render_to_string("loja/gestao/pdf/relatorio_produtos_pdf.html", {"produtos": produtos})
    html = weasyprint.HTML(string=html_string)

    # 🔹 Gera o PDF como resposta HTTP
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="relatorio_produtos.pdf"'
    html.write_pdf(response)

    return response

@login_required
@user_passes_test(admin_required)
def relatorio_pedidos(request):
    """
    Relatório de Pedidos – lista com filtros por número, cliente, status, valores e datas.
    """
    pedidos = Pedido.objects.all()

    # Filtros
    numero = request.GET.get("numero")
    cliente = request.GET.get("cliente")
    status = request.GET.get("status")
    valor_min = request.GET.get("valor_min")
    valor_max = request.GET.get("valor_max")
    data_inicio = request.GET.get("data_inicio")
    data_fim = request.GET.get("data_fim")

    if numero:
        pedidos = pedidos.filter(numero_pedido__icontains=numero)
    if cliente:
        pedidos = pedidos.filter(cliente__username__icontains=cliente)
    if status:
        pedidos = pedidos.filter(status=status)
    if valor_min:
        pedidos = pedidos.filter(total__gte=valor_min)
    if valor_max:
        pedidos = pedidos.filter(total__lte=valor_max)
    if data_inicio:
        pedidos = pedidos.filter(data_criacao__date__gte=data_inicio)
    if data_fim:
        pedidos = pedidos.filter(data_criacao__date__lte=data_fim)

    context = {"pedidos": pedidos}
    return render(request, "loja/gestao/relatorio_pedidos.html", context)

@login_required
@user_passes_test(admin_required)
def relatorio_pedidos_pdf(request):
    """
    Exporta o Relatório de Pedidos para PDF, aplicando os filtros da tela.
    """
    pedidos = Pedido.objects.all()

    # 🔹 Filtros (mesmos do relatorio_pedidos)
    numero = request.GET.get("numero")
    cliente = request.GET.get("cliente")
    status = request.GET.get("status")
    valor_min = request.GET.get("valor_min")
    valor_max = request.GET.get("valor_max")
    data_inicio = request.GET.get("data_inicio")
    data_fim = request.GET.get("data_fim")

    if numero:
        pedidos = pedidos.filter(numero_pedido__icontains=numero)
    if cliente:
        pedidos = pedidos.filter(cliente__username__icontains=cliente)
    if status:
        pedidos = pedidos.filter(status=status)
    if valor_min:
        pedidos = pedidos.filter(total__gte=valor_min)
    if valor_max:
        pedidos = pedidos.filter(total__lte=valor_max)
    if data_inicio:
        pedidos = pedidos.filter(data_criacao__date__gte=data_inicio)
    if data_fim:
        pedidos = pedidos.filter(data_criacao__date__lte=data_fim)

    # 🔹 Renderiza template PDF
    html_string = render_to_string("loja/gestao/pdf/relatorio_pedidos_pdf.html", {"pedidos": pedidos})
    html = weasyprint.HTML(string=html_string)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="relatorio_pedidos.pdf"'
    html.write_pdf(response)

    return response

@login_required
@user_passes_test(admin_required)
def relatorio_estoque(request):
    """
    Relatório de Estoque – lista com filtros por produto, tipo, quantidade e data.
    """
    movs = MovimentacaoEstoque.objects.all()

    # Filtros
    produto = request.GET.get("produto")
    tipo = request.GET.get("tipo")
    qtd_min = request.GET.get("qtd_min")
    qtd_max = request.GET.get("qtd_max")
    data_inicio = request.GET.get("data_inicio")
    data_fim = request.GET.get("data_fim")

    if produto:
        movs = movs.filter(produto__nome__icontains=produto)
    if tipo:
        movs = movs.filter(tipo=tipo)
    if qtd_min:
        movs = movs.filter(quantidade__gte=qtd_min)
    if qtd_max:
        movs = movs.filter(quantidade__lte=qtd_max)
    if data_inicio:
        movs = movs.filter(data__date__gte=data_inicio)
    if data_fim:
        movs = movs.filter(data__date__lte=data_fim)

    context = {"movs": movs}
    return render(request, "loja/gestao/relatorio_estoque.html", context)

@login_required
@user_passes_test(admin_required)
def relatorio_estoque_pdf(request):
    """
    Exporta o Relatório de Estoque para PDF, aplicando os filtros da tela.
    """
    movs = MovimentacaoEstoque.objects.all()

    # 🔹 Filtros (mesmos da view normal)
    produto = request.GET.get("produto")
    tipo = request.GET.get("tipo")
    qtd_min = request.GET.get("qtd_min")
    qtd_max = request.GET.get("qtd_max")
    data_inicio = request.GET.get("data_inicio")
    data_fim = request.GET.get("data_fim")

    if produto:
        movs = movs.filter(produto__nome__icontains=produto)
    if tipo:
        movs = movs.filter(tipo=tipo)
    if qtd_min:
        movs = movs.filter(quantidade__gte=qtd_min)
    if qtd_max:
        movs = movs.filter(quantidade__lte=qtd_max)
    if data_inicio:
        movs = movs.filter(data__date__gte=data_inicio)
    if data_fim:
        movs = movs.filter(data__date__lte=data_fim)

    # 🔹 Renderiza template PDF
    html_string = render_to_string("loja/gestao/pdf/relatorio_estoque_pdf.html", {"movs": movs})
    html = weasyprint.HTML(string=html_string)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="relatorio_estoque.pdf"'
    html.write_pdf(response)

    return response

@login_required
@user_passes_test(admin_required)
def relatorio_financeiro(request):
    """
    Relatório Financeiro – lista com filtros por categoria, tipo, valor e data.
    """
    lancamentos = LancamentoFinanceiro.objects.all()

    # Filtros
    categoria = request.GET.get("categoria")
    tipo_lancamento = request.GET.get("tipo_lancamento")
    valor_min = request.GET.get("valor_min")
    valor_max = request.GET.get("valor_max")
    data_inicio = request.GET.get("data_inicio")
    data_fim = request.GET.get("data_fim")

    if categoria:
        lancamentos = lancamentos.filter(categoria__icontains=categoria)
    if tipo_lancamento:
        lancamentos = lancamentos.filter(tipo=tipo_lancamento)
    if valor_min:
        lancamentos = lancamentos.filter(valor__gte=valor_min)
    if valor_max:
        lancamentos = lancamentos.filter(valor__lte=valor_max)
    if data_inicio:
        lancamentos = lancamentos.filter(data__gte=data_inicio)
    if data_fim:
        lancamentos = lancamentos.filter(data__lte=data_fim)

    context = {"lancamentos": lancamentos}
    return render(request, "loja/gestao/relatorio_financeiro.html", context)

@login_required
@user_passes_test(admin_required)
def relatorio_financeiro_pdf(request):
    """
    Exporta o Relatório Financeiro para PDF, aplicando os filtros da tela.
    """
    lancamentos = LancamentoFinanceiro.objects.all()

    # 🔹 Filtros (mesmos da view normal)
    categoria = request.GET.get("categoria")
    tipo_lancamento = request.GET.get("tipo_lancamento")
    valor_min = request.GET.get("valor_min")
    valor_max = request.GET.get("valor_max")
    data_inicio = request.GET.get("data_inicio")
    data_fim = request.GET.get("data_fim")

    if categoria:
        lancamentos = lancamentos.filter(categoria__icontains=categoria)
    if tipo_lancamento:
        lancamentos = lancamentos.filter(tipo=tipo_lancamento)
    if valor_min:
        lancamentos = lancamentos.filter(valor__gte=valor_min)
    if valor_max:
        lancamentos = lancamentos.filter(valor__lte=valor_max)
    if data_inicio:
        lancamentos = lancamentos.filter(data__gte=data_inicio)
    if data_fim:
        lancamentos = lancamentos.filter(data__lte=data_fim)

    # 🔹 Renderiza template PDF
    html_string = render_to_string("loja/gestao/pdf/relatorio_financeiro_pdf.html", {"lancamentos": lancamentos})
    html = weasyprint.HTML(string=html_string)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="relatorio_financeiro.pdf"'
    html.write_pdf(response)

    return response

@login_required
@user_passes_test(admin_required)
def relatorio_feedbacks(request):
    """
    Relatório de Feedbacks – lista com filtros por produto, usuário, nota e visibilidade.
    """
    feedbacks = Feedback.objects.all()

    # Filtros
    produto = request.GET.get("produto")
    usuario = request.GET.get("usuario")
    nota = request.GET.get("nota")
    visivel = request.GET.get("visivel")

    if produto:
        feedbacks = feedbacks.filter(produto__nome__icontains=produto)
    if usuario:
        feedbacks = feedbacks.filter(usuario__username__icontains=usuario)
    if nota:
        feedbacks = feedbacks.filter(nota=nota)
    if visivel in ["True", "False"]:
        feedbacks = feedbacks.filter(visivel=(visivel == "True"))

    context = {"feedbacks": feedbacks}
    return render(request, "loja/gestao/relatorio_feedbacks.html", context)

@login_required
@user_passes_test(admin_required)
def relatorio_feedbacks_pdf(request):
    """
    Exporta o Relatório de Feedbacks para PDF, aplicando os filtros da tela.
    """
    feedbacks = Feedback.objects.all()

    # 🔹 Filtros (mesmos da view normal)
    produto = request.GET.get("produto")
    usuario = request.GET.get("usuario")
    nota = request.GET.get("nota")
    visivel = request.GET.get("visivel")

    if produto:
        feedbacks = feedbacks.filter(produto__nome__icontains=produto)
    if usuario:
        feedbacks = feedbacks.filter(usuario__username__icontains=usuario)
    if nota:
        feedbacks = feedbacks.filter(nota=nota)
    if visivel in ["True", "False"]:
        feedbacks = feedbacks.filter(visivel=(visivel == "True"))

    # 🔹 Renderiza template PDF
    html_string = render_to_string("loja/gestao/pdf/relatorio_feedbacks_pdf.html", {"feedbacks": feedbacks})
    html = weasyprint.HTML(string=html_string)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="relatorio_feedbacks.pdf"'
    html.write_pdf(response)

    return response