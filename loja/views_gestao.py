from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.timezone import localtime
from .models import Produto, MovimentacaoEstoque

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
    # Lista de produtos
    produtos = Produto.objects.all().order_by("nome")

    # Card: total de produtos
    total_produtos = produtos.count()

    # Card: produtos com estoque baixo (<=5)
    produtos_baixo_estoque = produtos.filter(quantidade__lte=5).count()

    # Card: última movimentação (se existir)
    ultima_mov = MovimentacaoEstoque.objects.order_by("-data").first()
    ultima_movimentacao = localtime(ultima_mov.data).strftime("%d/%m/%Y %H:%M") if ultima_mov else "-"

    # Preparar dados para a tabela
    tabela_produtos = []
    for produto in produtos:
        # Percentual em relação a um limite fixo (podemos depois deixar dinâmico)
        limite_maximo = 25
        percentual = int((produto.quantidade / limite_maximo) * 100) if limite_maximo > 0 else 0

        # Cor da barra de estoque
        if produto.quantidade <= 5:
            cor = "bg-danger"
        elif produto.quantidade <= 10:
            cor = "bg-warning text-dark"
        else:
            cor = "bg-success"

        # Última movimentação daquele produto
        ultima_mov_produto = MovimentacaoEstoque.objects.filter(produto=produto).order_by("-data").first()
        data_mov = localtime(ultima_mov_produto.data).strftime("%d/%m/%Y %H:%M") if ultima_mov_produto else "-"

        tabela_produtos.append({
            "nome": produto.nome,
            "quantidade": produto.quantidade,
            "percentual": percentual if percentual <= 100 else 100,
            "cor": cor,
            "ultima_atualizacao": data_mov,
        })

    context = {
        "total_produtos": total_produtos,
        "produtos_baixo_estoque": produtos_baixo_estoque,
        "ultima_movimentacao": ultima_movimentacao,
        "tabela_produtos": tabela_produtos,
    }
    return render(request, "loja/gestao/estoque.html", context)


