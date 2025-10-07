from collections import defaultdict
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Sum
from django.utils.timezone import localtime
from django.db import models
from .models import Produto, CustoProduto, Pedido, PedidoItem, Despesa, Produto, MovimentacaoEstoque,LancamentoFinanceiro, Feedback, HistoricoCusto
from .forms import DespesaForm
from datetime import datetime, time
from dateutil.relativedelta import relativedelta
import weasyprint
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.db.models.functions import TruncMonth
from django.utils import timezone
import locale
from django.utils.dateparse import parse_date
from decimal import Decimal, InvalidOperation

# Defina o locale para português (Windows pode precisar de 'pt_BR')
try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
except:
    locale.setlocale(locale.LC_TIME, 'Portuguese_Brazil')

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
    from .models import Produto, CustoProduto, HistoricoCusto

    # 🔹 Filtro por nome
    nome = request.GET.get("nome")
    produtos = Produto.objects.all().order_by("nome")
    if nome:
        produtos = produtos.filter(nome__icontains=nome)

    if request.method == "POST":
        for produto in produtos:
            novo_custo_raw = request.POST.get(f"custo_{produto.id}")
            if not novo_custo_raw:
                continue

            try:
                novo_custo = float(novo_custo_raw)
            except ValueError:
                continue

            custo_obj, _ = CustoProduto.objects.get_or_create(produto=produto)

            # 🔹 Se mudou o valor, grava histórico antes de atualizar
            if custo_obj.custo != novo_custo:
                HistoricoCusto.objects.create(
                    produto=produto,
                    custo_antigo=custo_obj.custo,
                    custo_novo=novo_custo,
                    usuario=request.user
                )

                custo_obj.custo = novo_custo
                custo_obj.save()

        messages.success(request, "Custos atualizados com sucesso!")
        return redirect("financeiro_produtos")

    # Contexto para exibir tabela
    produtos_data = []
    for p in produtos:
        # Evita erro se não existir custo_info
        custo_atual = getattr(p, "custo_info", None)
        custo_valor = custo_atual.custo if custo_atual else 0

        margem = None
        lucro_unitario = None
        if custo_valor > 0:
            lucro_unitario = p.preco - custo_valor
            margem = (lucro_unitario / custo_valor) * 100

        produtos_data.append({
            "produto": p,
            "custo": custo_valor,
            "preco": p.preco,
            "lucro_unitario": lucro_unitario,
            "margem": margem,
        })

    context = {"produtos_data": produtos_data}
    return render(request, "loja/gestao/financeiro_produtos.html", context)



@login_required
@user_passes_test(admin_required)
def historico_custo(request):
    from datetime import datetime, timedelta, time
    from django.utils.dateparse import parse_date

    today = datetime.today()
    data_inicio_str = request.GET.get("data_inicio") or request.session.get("data_inicio")
    data_fim_str = request.GET.get("data_fim") or request.session.get("data_fim")

    if not data_inicio_str or not data_fim_str:
        primeiro_dia = today.replace(day=1).date()
        if today.month == 12:
            proximo_mes = today.replace(year=today.year + 1, month=1, day=1)
        else:
            proximo_mes = today.replace(month=today.month + 1, day=1)
        ultimo_dia = (proximo_mes - timedelta(days=1)).date()
        data_inicio_str = data_inicio_str or primeiro_dia.isoformat()
        data_fim_str = data_fim_str or ultimo_dia.isoformat()

    request.session["data_inicio"] = data_inicio_str
    request.session["data_fim"] = data_fim_str

    di = parse_date(data_inicio_str)
    df = parse_date(data_fim_str)
    dt_inicio = datetime.combine(di, time.min) if di else None
    dt_fim = datetime.combine(df, time.max) if df else None

    historicos = HistoricoCusto.objects.select_related("produto", "usuario").order_by("-data")
    if dt_inicio:
        historicos = historicos.filter(data__gte=dt_inicio)
    if dt_fim:
        historicos = historicos.filter(data__lte=dt_fim)

    context = {
        "historicos": historicos,
        "data_inicio": di.isoformat() if di else "",
        "data_fim": df.isoformat() if df else "",
    }
    return render(request, "loja/gestao/historico_custo.html", context)

@login_required
@user_passes_test(admin_required)
def financeiro_pedidos(request):
    from datetime import datetime, timedelta, time
    from django.utils.dateparse import parse_date

    today = datetime.today()
    data_inicio_str = request.GET.get("data_inicio") or request.session.get("data_inicio")
    data_fim_str = request.GET.get("data_fim") or request.session.get("data_fim")

    if not data_inicio_str or not data_fim_str:
        primeiro_dia = today.replace(day=1).date()
        if today.month == 12:
            proximo_mes = today.replace(year=today.year + 1, month=1, day=1)
        else:
            proximo_mes = today.replace(month=today.month + 1, day=1)
        ultimo_dia = (proximo_mes - timedelta(days=1)).date()
        data_inicio_str = data_inicio_str or primeiro_dia.isoformat()
        data_fim_str = data_fim_str or ultimo_dia.isoformat()

    request.session["data_inicio"] = data_inicio_str
    request.session["data_fim"] = data_fim_str

    di = parse_date(data_inicio_str)
    df = parse_date(data_fim_str)
    dt_inicio = datetime.combine(di, time.min) if di else None
    dt_fim = datetime.combine(df, time.max) if df else None

    pedidos = Pedido.objects.filter(status="Pago").select_related("cliente").order_by("-data_criacao")
    if dt_inicio:
        pedidos = pedidos.filter(data_criacao__gte=dt_inicio)
    if dt_fim:
        pedidos = pedidos.filter(data_criacao__lte=dt_fim)

    pedidos_data = []
    for p in pedidos:
        receita = float(p.total or 0)
        itens = PedidoItem.objects.filter(pedido=p)
        custo_total = sum(float(item.custo_unitario) * item.quantidade for item in itens)
        lucro = receita - custo_total
        pedidos_data.append({
            "numero": p.numero_pedido or p.id,
            "cliente": getattr(p.cliente, "username", "-"),
            "data": p.data_criacao.strftime("%d/%m/%Y") if p.data_criacao else "-",
            "receita": receita,
            "custo": float(custo_total),
            "lucro": float(lucro),
        })

    context = {
        "pedidos_data": pedidos_data,
        "data_inicio": di.isoformat() if di else "",
        "data_fim": df.isoformat() if df else "",
    }
    return render(request, "loja/gestao/financeiro_pedidos.html", context)

@login_required
@user_passes_test(admin_required)
def financeiro_resumo(request):
    from datetime import datetime, timedelta, time
    from django.utils.dateparse import parse_date
    from collections import defaultdict
    from calendar import monthrange

    today = datetime.today()

    # 🔹 Tenta pegar da URL
    data_inicio_str = request.GET.get("data_inicio")
    data_fim_str = request.GET.get("data_fim")

    # 🔹 Se não vier, usa da sessão
    if not data_inicio_str:
        data_inicio_str = request.session.get("data_inicio")
    if not data_fim_str:
        data_fim_str = request.session.get("data_fim")

    # 🔹 Se ainda não tiver nada, aplica padrão = mês atual
    if not data_inicio_str or not data_fim_str:
        primeiro_dia = today.replace(day=1).date()
        if today.month == 12:
            proximo_mes = today.replace(year=today.year + 1, month=1, day=1)
        else:
            proximo_mes = today.replace(month=today.month + 1, day=1)
        ultimo_dia = (proximo_mes - timedelta(days=1)).date()
        data_inicio_str = data_inicio_str or primeiro_dia.isoformat()
        data_fim_str = data_fim_str or ultimo_dia.isoformat()

    # 🔹 Salva na sessão
    request.session["data_inicio"] = data_inicio_str
    request.session["data_fim"] = data_fim_str

    di = parse_date(data_inicio_str)
    df = parse_date(data_fim_str)
    dt_inicio = datetime.combine(di, time.min) if di else None
    dt_fim = datetime.combine(df, time.max) if df else None

    # 🔹 QuerySets
    pedidos = Pedido.objects.filter(status="Pago")
    if dt_inicio:
        pedidos = pedidos.filter(data_criacao__gte=dt_inicio)
    if dt_fim:
        pedidos = pedidos.filter(data_criacao__lte=dt_fim)

    despesas = Despesa.objects.all()
    if di:
        despesas = despesas.filter(data__gte=di)
    if df:
        despesas = despesas.filter(data__lte=df)

    # 🔹 Indicadores
    receita_total = float(pedidos.aggregate(total=Sum("total"))["total"] or 0)

    custo_total = sum(
        float(item.custo_unitario) * item.quantidade
        for item in PedidoItem.objects.filter(pedido__in=pedidos)
    )

    despesas_fixas_valor = float(despesas.filter(tipo="Fixo").aggregate(total=Sum("valor"))["total"] or 0)
    despesas_variaveis_valor = float(despesas.filter(tipo="Variável").aggregate(total=Sum("valor"))["total"] or 0)
    lucro_liquido = receita_total - custo_total - despesas_fixas_valor - despesas_variaveis_valor

    # 🔹 Gráficos (resumido do que você já tinha)
    receitas_por_mes, despesas_por_mes, custos_por_mes = defaultdict(float), defaultdict(float), defaultdict(float)
    for p in pedidos:
        if p.data_criacao:
            mes_label = p.data_criacao.strftime("%b/%y").capitalize()
            receitas_por_mes[mes_label] += float(p.total or 0)
            for it in p.itens.all():
                custos_por_mes[mes_label] += float(it.custo_unitario) * it.quantidade
    for d in despesas:
        if d.data:
            mes_label = d.data.strftime("%b/%y").capitalize()
            despesas_por_mes[mes_label] += float(d.valor or 0)

    meses = sorted(set(receitas_por_mes.keys()) | set(despesas_por_mes.keys()) | set(custos_por_mes.keys()))
    receitas_grafico = [receitas_por_mes[m] for m in meses]
    despesas_grafico = [despesas_por_mes[m] + custos_por_mes[m] for m in meses]

    if len(meses) == 1:
        lucro_por_dia = defaultdict(float)
        dias, mes_ano = set(), None
        for p in pedidos:
            dia = p.data_criacao.strftime("%d")
            custo_p = sum(float(it.custo_unitario) * it.quantidade for it in p.itens.all())
            despesa_dia = float(despesas.filter(data=p.data_criacao.date()).aggregate(total=Sum("valor"))["total"] or 0)
            lucro_por_dia[dia] += float(p.total or 0) - custo_p - despesa_dia
            dias.add(dia)
            if not mes_ano:
                mes_ano = p.data_criacao.strftime("%Y-%m")
        if not mes_ano:
            mes_ano = di.strftime("%Y-%m") if di else today.strftime("%Y-%m")
        ano, mes = map(int, mes_ano.split("-"))
        num_dias = monthrange(ano, mes)[1]
        labels_lucro = [f"{str(d).zfill(2)}" for d in range(1, num_dias + 1)]
        dados_lucro = [lucro_por_dia[l] if l in lucro_por_dia else 0 for l in labels_lucro]
    else:
        lucro_por_mes = defaultdict(float)
        pedidos_por_mes = defaultdict(list)
        for p in pedidos:
            chave = p.data_criacao.strftime("%Y-%m")
            pedidos_por_mes[chave].append(p)
        despesas_por_mes_calc = defaultdict(float)
        for d in despesas:
            chave = d.data.strftime("%Y-%m")
            despesas_por_mes_calc[chave] += float(d.valor or 0)
        todos_meses = sorted(set(pedidos_por_mes.keys()) | set(despesas_por_mes_calc.keys()))
        for chave in todos_meses:
            receita = sum(float(p.total or 0) for p in pedidos_por_mes.get(chave, []))
            custo_mes = sum(float(it.custo_unitario) * it.quantidade for p in pedidos_por_mes.get(chave, []) for it in p.itens.all())
            despesas_mes_valor = despesas_por_mes_calc.get(chave, 0.0)
            lucro_por_mes[chave] = receita - custo_mes - despesas_mes_valor
        labels_lucro = [datetime.strptime(ch, "%Y-%m").strftime("%b/%y").capitalize() for ch in todos_meses]
        dados_lucro = [lucro_por_mes[ch] for ch in todos_meses]

    context = {
        "receita_total": receita_total,
        "custo_total": custo_total,
        "lucro_liquido": lucro_liquido,
        "despesas_fixas": despesas_fixas_valor,
        "despesas_variaveis": despesas_variaveis_valor,
        "data_inicio": di.isoformat() if di else "",
        "data_fim": df.isoformat() if df else "",
        "meses_grafico": meses,
        "receitas_grafico": receitas_grafico,
        "despesas_grafico": despesas_grafico,
        "labels_lucro": labels_lucro,
        "dados_lucro": dados_lucro,
    }
    return render(request, "loja/gestao/financeiro_resumo.html", context)

@login_required
@user_passes_test(admin_required)
def gestao_despesas(request):
    from django.core.paginator import Paginator
    from datetime import datetime, timedelta
    from django.db.models import Q

    despesas = Despesa.objects.all().order_by("-data")

    # 🔹 Filtros GET
    q = request.GET.get("q", "")
    tipo = request.GET.get("tipo", "")
    data_inicio = request.GET.get("data_inicio", "")
    data_fim = request.GET.get("data_fim", "")
    valor_min = request.GET.get("valor_min", "")
    valor_max = request.GET.get("valor_max", "")

    # 🔹 Filtro de busca (categoria ou descrição)
    if q:
        despesas = despesas.filter(Q(categoria__icontains=q) | Q(descricao__icontains=q))

    # 🔹 Filtro por tipo
    if tipo:
        despesas = despesas.filter(tipo=tipo)

    # 🔹 Filtro por intervalo de datas
    try:
        if data_inicio:
            inicio = datetime.strptime(data_inicio, "%Y-%m-%d")
            despesas = despesas.filter(data__gte=inicio)
        if data_fim:
            fim = datetime.strptime(data_fim, "%Y-%m-%d") + timedelta(days=1)
            despesas = despesas.filter(data__lt=fim)
    except ValueError:
        pass

    # 🔹 Filtro por faixa de valor
    if valor_min:
        despesas = despesas.filter(valor__gte=valor_min)
    if valor_max:
        despesas = despesas.filter(valor__lte=valor_max)

    # 🔹 Paginação
    paginator = Paginator(despesas, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # 🔹 Mantém filtros nos links da paginação
    filtro_params = request.GET.copy()
    if "page" in filtro_params:
        filtro_params.pop("page")
    filtro_params = filtro_params.urlencode()

    context = {
        "despesas": page_obj,
        "filtros": {
            "q": q,
            "tipo": tipo,
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "valor_min": valor_min,
            "valor_max": valor_max,
        },
        "filtro_params": filtro_params,
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
        despesa.categoria = request.POST.get("categoria")
        despesa.tipo = request.POST.get("tipo")
        despesa.valor = request.POST.get("valor")
        despesa.data = request.POST.get("data")
        despesa.descricao = request.POST.get("descricao")
        despesa.save()

        messages.success(request, "Despesa atualizada com sucesso!")
        return redirect("gestao_despesas")

    return render(request, "loja/gestao/editar_despesa.html", {"despesa": despesa})

@login_required
@user_passes_test(admin_required)
def excluir_despesa(request, pk):
    despesa = get_object_or_404(Despesa, pk=pk)
    if request.method == "POST":
        despesa.delete()
        messages.success(request, "Despesa excluída com sucesso!")
        return redirect("gestao_despesas")

    return render(request, "loja/gestao/excluir_despesa.html", {"despesa": despesa})

@login_required
@user_passes_test(admin_required)
def detalhes_despesa(request, pk):
    despesa = get_object_or_404(Despesa, pk=pk)
    return render(request, "loja/gestao/detalhes_despesa.html", {"despesa": despesa})

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
    Relatório de Pedidos – lista com filtros corrigidos (valor e data).
    Inclui custo_total e ordena do mais recente para o mais antigo.
    """
    pedidos = Pedido.objects.all().prefetch_related("itens", "cliente").order_by("-data_criacao")

    # 🔎 Filtros
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

    # ✅ Filtro por valores
    try:
        if valor_min:
            pedidos = pedidos.filter(total__gte=Decimal(valor_min))
        if valor_max:
            pedidos = pedidos.filter(total__lte=Decimal(valor_max))
    except (InvalidOperation, ValueError):
        pass  # ignora valores inválidos sem quebrar

    # ✅ Filtro por datas
    data_inicio_raw = request.GET.get("data_inicio")
    data_fim_raw = request.GET.get("data_fim")

    if data_inicio_raw:
        data_inicio = parse_date(data_inicio_raw)
        if data_inicio:
            dt_inicio = datetime.combine(data_inicio, time.min)  # 00:00:00
            pedidos = pedidos.filter(data_criacao__gte=dt_inicio)

    if data_fim_raw:
        data_fim = parse_date(data_fim_raw)
        if data_fim:
            dt_fim = datetime.combine(data_fim, time.max)  # 23:59:59
            pedidos = pedidos.filter(data_criacao__lte=dt_fim)

    # 🔹 Calcula custo_total
    pedidos_data = []
    for p in pedidos:
        custo_total = sum(item.quantidade * item.custo_unitario for item in p.itens.all())
        pedidos_data.append({
            "id": p.id,
            "numero_pedido": p.numero_pedido,
            "cliente": p.cliente,
            "total": p.total,
            "custo_total": custo_total,
            "status": p.status,
            "data_criacao": p.data_criacao,
        })

    context = {"pedidos": pedidos_data}
    return render(request, "loja/gestao/relatorio_pedidos.html", context)

@login_required
@user_passes_test(admin_required)
def relatorio_pedidos_pdf(request):
    """
    Exporta o Relatório de Pedidos para PDF, aplicando os mesmos filtros da tela.
    Inclui coluna de custo e ordena do mais recente para o mais antigo.
    """
    pedidos = Pedido.objects.all().prefetch_related("itens", "cliente").order_by("-data_criacao")

    # 🔎 Filtros
    numero = request.GET.get("numero")
    cliente = request.GET.get("cliente")
    status = request.GET.get("status")
    valor_min = request.GET.get("valor_min")
    valor_max = request.GET.get("valor_max")
    data_inicio_raw = request.GET.get("data_inicio")
    data_fim_raw = request.GET.get("data_fim")

    if numero:
        pedidos = pedidos.filter(numero_pedido__icontains=numero)
    if cliente:
        pedidos = pedidos.filter(cliente__username__icontains=cliente)
    if status:
        pedidos = pedidos.filter(status=status)

    # ✅ Filtro por valores
    try:
        if valor_min:
            pedidos = pedidos.filter(total__gte=Decimal(valor_min))
        if valor_max:
            pedidos = pedidos.filter(total__lte=Decimal(valor_max))
    except (InvalidOperation, ValueError):
        pass

    # ✅ Filtro por datas (corrigido p/ DateTimeField)
    if data_inicio_raw:
        data_inicio = parse_date(data_inicio_raw)
        if data_inicio:
            dt_inicio = datetime.combine(data_inicio, time.min)
            pedidos = pedidos.filter(data_criacao__gte=dt_inicio)

    if data_fim_raw:
        data_fim = parse_date(data_fim_raw)
        if data_fim:
            dt_fim = datetime.combine(data_fim, time.max)
            pedidos = pedidos.filter(data_criacao__lte=dt_fim)

    # 🔹 Calcula custo_total
    pedidos_data = []
    for p in pedidos:
        custo_total = sum(item.quantidade * item.custo_unitario for item in p.itens.all())
        pedidos_data.append({
            "id": p.id,
            "numero_pedido": p.numero_pedido,
            "cliente": p.cliente,
            "total": p.total,
            "custo_total": custo_total,
            "status": p.status,
            "data_criacao": p.data_criacao,
        })

    # 🔹 Renderiza template PDF
    html_string = render_to_string(
        "loja/gestao/pdf/relatorio_pedidos_pdf.html",
        {"pedidos": pedidos_data}
    )
    html = weasyprint.HTML(string=html_string)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="relatorio_pedidos.pdf"'
    html.write_pdf(response)

    return response

from django.utils.dateparse import parse_date
from datetime import datetime, time

@login_required
@user_passes_test(admin_required)
def relatorio_estoque(request):
    """
    Relatório de Estoque – lista com filtros por produto, tipo e data.
    """
    movs = MovimentacaoEstoque.objects.select_related("produto").all().order_by("-data")  # 🔹 mais recente primeiro

    # Filtros
    produto = request.GET.get("produto")
    tipo = request.GET.get("tipo")
    data_inicio_raw = request.GET.get("data_inicio")
    data_fim_raw = request.GET.get("data_fim")

    if produto:
        movs = movs.filter(produto__nome__icontains=produto)
    if tipo:
        movs = movs.filter(tipo=tipo)

    if data_inicio_raw:
        data_inicio = parse_date(data_inicio_raw)
        if data_inicio:
            dt_inicio = datetime.combine(data_inicio, time.min)
            movs = movs.filter(data__gte=dt_inicio)

    if data_fim_raw:
        data_fim = parse_date(data_fim_raw)
        if data_fim:
            dt_fim = datetime.combine(data_fim, time.max)
            movs = movs.filter(data__lte=dt_fim)

    context = {"movs": movs}
    return render(request, "loja/gestao/relatorio_estoque.html", context)

@login_required
@user_passes_test(admin_required)
def relatorio_estoque_pdf(request):
    """
    Exporta o Relatório de Estoque para PDF, aplicando os filtros da tela.
    """
    movs = MovimentacaoEstoque.objects.select_related("produto").all().order_by("-data")  # 🔹 mais recente primeiro

    # Filtros
    produto = request.GET.get("produto")
    tipo = request.GET.get("tipo")
    data_inicio_raw = request.GET.get("data_inicio")
    data_fim_raw = request.GET.get("data_fim")

    if produto:
        movs = movs.filter(produto__nome__icontains=produto)
    if tipo:
        movs = movs.filter(tipo=tipo)

    if data_inicio_raw:
        data_inicio = parse_date(data_inicio_raw)
        if data_inicio:
            dt_inicio = datetime.combine(data_inicio, time.min)
            movs = movs.filter(data__gte=dt_inicio)

    if data_fim_raw:
        data_fim = parse_date(data_fim_raw)
        if data_fim:
            dt_fim = datetime.combine(data_fim, time.max)
            movs = movs.filter(data__lte=dt_fim)

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
    Relatório Financeiro – exibe valores DIÁRIOS (receita, custo, despesas fixas/variáveis e lucro líquido).
    Permite ordenar por data (padrão), receita, custo, fixa, variável ou lucro.
    """

    # 📌 Filtros de data (agora opcionais, se não passar mostra tudo)
    data_inicio_raw = request.GET.get("data_inicio")
    data_fim_raw = request.GET.get("data_fim")

    data_inicio = parse_date(data_inicio_raw) if data_inicio_raw else None
    data_fim = parse_date(data_fim_raw) if data_fim_raw else None

    # Busca bruta
    pedidos = Pedido.objects.filter(status="Pago")
    despesas = Despesa.objects.all()

    if data_inicio:
        dt_inicio = datetime.combine(data_inicio, time.min)
        pedidos = pedidos.filter(data_criacao__gte=dt_inicio)
        despesas = despesas.filter(data__gte=data_inicio)

    if data_fim:
        dt_fim = datetime.combine(data_fim, time.max)
        pedidos = pedidos.filter(data_criacao__lte=dt_fim)
        despesas = despesas.filter(data__lte=data_fim)

    # 📅 Monta estrutura por dia
    from collections import defaultdict
    dados_diarios = defaultdict(lambda: {"receita": 0, "custo": 0, "fixa": 0, "variavel": 0})

    for p in pedidos:
        dia = p.data_criacao.date()
        dados_diarios[dia]["receita"] += float(p.total or 0)
        for item in p.itens.all():
            dados_diarios[dia]["custo"] += float(item.custo_unitario) * item.quantidade

    for d in despesas:
        if d.tipo == "Fixo":
            dados_diarios[d.data]["fixa"] += float(d.valor or 0)
        elif d.tipo == "Variável":
            dados_diarios[d.data]["variavel"] += float(d.valor or 0)

    # Monta lista final
    tabela = []
    for dia, valores in dados_diarios.items():
        receita = valores["receita"]
        custo = valores["custo"]
        fixa = valores["fixa"]
        variavel = valores["variavel"]
        lucro = receita - custo - fixa - variavel

        tabela.append({
            "data": dia,
            "receita": receita,
            "custo": custo,
            "fixa": fixa,
            "variavel": variavel,
            "lucro": lucro,
        })

    # 🔽 Ordenação
    ordenar_por = request.GET.get("ordenar_por")
    if ordenar_por in ["receita", "custo", "fixa", "variavel", "lucro"]:
        tabela = sorted(tabela, key=lambda x: x[ordenar_por], reverse=True)
    else:
        tabela = sorted(tabela, key=lambda x: x["data"], reverse=True)  # padrão: mais recente → mais antigo

    context = {
        "tabela": tabela,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "ordenar_por": ordenar_por or "data",
    }
    return render(request, "loja/gestao/relatorio_financeiro.html", context)

@login_required
@user_passes_test(admin_required)
def relatorio_financeiro_pdf(request):
    """
    Exporta o Relatório Financeiro Diário para PDF, aplicando os filtros da tela.
    """

    # 📌 Filtros de data (iguais ao HTML)
    data_inicio_raw = request.GET.get("data_inicio")
    data_fim_raw = request.GET.get("data_fim")

    data_inicio = parse_date(data_inicio_raw) if data_inicio_raw else None
    data_fim = parse_date(data_fim_raw) if data_fim_raw else None

    pedidos = Pedido.objects.filter(status="Pago")
    despesas = Despesa.objects.all()

    if data_inicio:
        dt_inicio = datetime.combine(data_inicio, time.min)
        pedidos = pedidos.filter(data_criacao__gte=dt_inicio)
        despesas = despesas.filter(data__gte=data_inicio)

    if data_fim:
        dt_fim = datetime.combine(data_fim, time.max)
        pedidos = pedidos.filter(data_criacao__lte=dt_fim)
        despesas = despesas.filter(data__lte=data_fim)

    # 📅 Monta estrutura por dia
    from collections import defaultdict
    dados_diarios = defaultdict(lambda: {"receita": 0, "custo": 0, "fixa": 0, "variavel": 0})

    for p in pedidos:
        dia = p.data_criacao.date()
        dados_diarios[dia]["receita"] += float(p.total or 0)
        for item in p.itens.all():
            dados_diarios[dia]["custo"] += float(item.custo_unitario) * item.quantidade

    for d in despesas:
        if d.tipo == "Fixo":
            dados_diarios[d.data]["fixa"] += float(d.valor or 0)
        elif d.tipo == "Variável":
            dados_diarios[d.data]["variavel"] += float(d.valor or 0)

    # Monta lista final
    tabela = []
    for dia, valores in dados_diarios.items():
        receita = valores["receita"]
        custo = valores["custo"]
        fixa = valores["fixa"]
        variavel = valores["variavel"]
        lucro = receita - custo - fixa - variavel

        tabela.append({
            "data": dia,
            "receita": receita,
            "custo": custo,
            "fixa": fixa,
            "variavel": variavel,
            "lucro": lucro,
        })

    # 🔽 Ordenação
    ordenar_por = request.GET.get("ordenar_por")
    if ordenar_por in ["receita", "custo", "fixa", "variavel", "lucro"]:
        tabela = sorted(tabela, key=lambda x: x[ordenar_por], reverse=True)
    else:
        tabela = sorted(tabela, key=lambda x: x["data"], reverse=True)

    # 🔹 Renderiza template PDF
    html_string = render_to_string("loja/gestao/pdf/relatorio_financeiro_pdf.html", {
        "tabela": tabela,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "ordenar_por": ordenar_por or "data",
    })
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