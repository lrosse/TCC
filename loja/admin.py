from django.contrib import admin
from .models import Produto, Feedback, Pedido, PedidoItem

@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'preco', 'descricao')
    search_fields = ('nome',)

# Novo registro para Feedback
@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'produto', 'pedido', 'nota', 'data_criacao', 'data_atualizacao')
    list_filter = ('nota', 'data_criacao')
    search_fields = ('usuario__username', 'comentario')
    
# 🔹 Novo registro para Pedido
@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ('numero_pedido', 'cliente', 'status', 'total', 'data_criacao')
    search_fields = ('numero_pedido', 'cliente__username')
    list_filter = ('status', 'data_criacao')

# 🔹 Novo registro para PedidoItem
@admin.register(PedidoItem)
class PedidoItemAdmin(admin.ModelAdmin):
    list_display = ('pedido', 'nome_produto', 'quantidade', 'preco_unitario', 'custo_unitario')
    search_fields = ('nome_produto', 'pedido__numero_pedido')
