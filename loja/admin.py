from django.contrib import admin
from .models import Produto, Feedback

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
