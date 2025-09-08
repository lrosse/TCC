from datetime import timezone
import json
import csv
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.timezone import localtime
from django.contrib import messages
from django.db import models
from django.http import JsonResponse
from django.http import HttpResponse
from .models import Produto, MovimentacaoEstoque, Pedido, LancamentoFinanceiro
from django.db.models import Sum
from .views import (
    _agregar_vendas_por_mes,
    _agregar_vendas_mes_atual_por_dia,
    _contagem_pedidos_por_status
)
from reportlab.pdfgen import canvas 



def admin_required(user):
    return user.is_staff or user.is_superuser

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
            quantidade__lt=models.F("ideal_estoque")
        )
    elif filtro == "alto":
        produtos = produtos.filter(quantidade__gte=models.F("ideal_estoque"))

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

    # Cards
    total_produtos = produtos.count()
    produtos_baixo_estoque = produtos.filter(quantidade__lte=models.F("minimo_estoque")).count()
    ultima_mov = MovimentacaoEstoque.objects.order_by("-data").first()
    ultima_movimentacao = localtime(ultima_mov.data).strftime("%d/%m/%Y %H:%M") if ultima_mov else "-"

    maior_estoque = produtos.aggregate(models.Max("quantidade"))["quantidade__max"] or 1

    tabela_produtos = []
    for produto in produtos:
        percentual = int((produto.quantidade / maior_estoque) * 100)
        if produto.quantidade <= produto.minimo_estoque:
            cor = "bg-danger"
        elif produto.quantidade <= produto.ideal_estoque:
            cor = "bg-warning text-dark"
        else:
            cor = "bg-success"

        ultima_mov_produto = MovimentacaoEstoque.objects.filter(produto=produto).order_by("-data").first()
        data_mov = localtime(ultima_mov_produto.data).strftime("%d/%m/%Y %H:%M") if ultima_mov_produto else "-"

        tabela_produtos.append({
            "id": produto.id,
            "nome": produto.nome,
            "quantidade": produto.quantidade,
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
def financeiro(request):
    pedidos_pagos = Pedido.objects.filter(status="Pago")
    lancamentos = LancamentoFinanceiro.objects.all().order_by("-data")

    # Filtros
    tipo = request.GET.get("tipo")
    categoria = request.GET.get("categoria")
    data_inicio = request.GET.get("data_inicio")
    data_fim = request.GET.get("data_fim")

    if tipo:
        lancamentos = lancamentos.filter(tipo=tipo)
    if categoria:
        lancamentos = lancamentos.filter(categoria__icontains=categoria)
    if data_inicio:
        lancamentos = lancamentos.filter(data__gte=data_inicio)
    if data_fim:
        lancamentos = lancamentos.filter(data__lte=data_fim)

    # Totais
    receitas_pedidos = pedidos_pagos.aggregate(total=Sum("total"))["total"] or 0
    receitas_extras = lancamentos.filter(tipo="receita").aggregate(total=Sum("valor"))["total"] or 0
    despesas = lancamentos.filter(tipo="despesa").aggregate(total=Sum("valor"))["total"] or 0
    total_receitas = receitas_pedidos + receitas_extras
    lucro_liquido = total_receitas - despesas

    # Gráficos
    mes_labels, mes_values = _agregar_vendas_por_mes(pedidos_pagos)
    dia_labels, dia_values = _agregar_vendas_mes_atual_por_dia(pedidos_pagos)

    despesas_por_categoria = (
        LancamentoFinanceiro.objects.filter(tipo="despesa")
        .values("categoria")
        .annotate(total=Sum("valor"))
        .order_by("-total")
    )
    categorias_labels = [d["categoria"] for d in despesas_por_categoria]
    categorias_values = [float(d["total"]) for d in despesas_por_categoria]

    context = {
        "receitas_pedidos": receitas_pedidos,
        "receitas_extras": receitas_extras,
        "despesas": despesas,
        "total_receitas": total_receitas,
        "lucro_liquido": lucro_liquido,
        "lancamentos": lancamentos,
        "mes_labels_json": json.dumps(mes_labels, ensure_ascii=False),
        "mes_values_json": json.dumps(mes_values),
        "dia_labels_json": json.dumps(dia_labels, ensure_ascii=False),
        "dia_values_json": json.dumps(dia_values),
        "cat_labels_json": json.dumps(categorias_labels, ensure_ascii=False),
        "cat_values_json": json.dumps(categorias_values),
        "filtros": {"tipo": tipo, "categoria": categoria, "data_inicio": data_inicio, "data_fim": data_fim},
    }
    return render(request, "loja/gestao/financeiro.html", context)


@login_required
@user_passes_test(admin_required)
def adicionar_lancamento(request):
    tipo = request.POST.get("tipo")
    categoria = request.POST.get("categoria")
    valor = request.POST.get("valor")
    data = request.POST.get("data")
    descricao = request.POST.get("descricao", "")

    if tipo and categoria and valor:
        LancamentoFinanceiro.objects.create(
            tipo=tipo,
            categoria=categoria,
            valor=valor,
            data=data or timezone.now().date(),
            descricao=descricao
        )
        messages.success(request, "Lançamento adicionado com sucesso!")
    else:
        messages.error(request, "Preencha todos os campos obrigatórios.")

    return redirect("financeiro")

@user_passes_test(admin_required)
def exportar_financeiro_csv(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="financeiro.csv"'

    writer = csv.writer(response)
    writer.writerow(["Data", "Tipo", "Categoria", "Valor", "Descrição"])

    for l in LancamentoFinanceiro.objects.all().order_by("-data"):
        writer.writerow([l.data, l.get_tipo_display(), l.categoria, l.valor, l.descricao or ""])

    return response

@user_passes_test(admin_required)
def exportar_financeiro_pdf(request):
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="financeiro.pdf"'

    p = canvas.Canvas(response)
    p.setFont("Helvetica", 12)
    p.drawString(100, 800, "Relatório Financeiro")

    y = 760
    for l in LancamentoFinanceiro.objects.all().order_by("-data")[:50]:
        p.drawString(100, y, f"{l.data} - {l.get_tipo_display()} - {l.categoria} - R$ {l.valor}")
        y -= 20
        if y < 100:
            p.showPage()
            y = 800

    p.showPage()
    p.save()
    return response
