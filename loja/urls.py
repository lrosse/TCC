from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', views.home, name='home'),
    path('registrar/', views.registrar, name='registrar'),
    path('entrar/', views.entrar, name='login'),
    path('sair/', views.sair, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Rotas para produtos
    path('produtos/criar/', views.criar_produto, name='criar_produto'),
    path('produtos/listar/', views.listar_produtos, name='listar_produtos'),
    path('produtos/editar/<int:produto_id>/', views.editar_produto, name='editar_produto'),
    path('produtos/excluir/<int:produto_id>/', views.excluir_produto, name='excluir_produto'),
    path('produto/<int:produto_id>/', views.produto_detalhe, name='produto_detalhe'),


    # Rotas para estoque
    path('produtos/entrada-estoque/', views.entrada_estoque, name='entrada_estoque'),
    path('produtos/ajuste-estoque/', views.ajuste_estoque, name='ajuste_estoque'),
    path('produtos/historico-estoque/', views.historico_estoque, name='historico_estoque'),

    
    # Rotas para carrinho
    path('carrinho/adicionar/<int:produto_id>/', views.adicionar_ao_carrinho, name='adicionar_ao_carrinho'),
    path('carrinho/', views.ver_carrinho, name='ver_carrinho'),
    path('carrinho/remover/<int:item_id>/', views.remover_do_carrinho, name='remover_do_carrinho'),
    path('carrinho/alterar/<int:item_id>/', views.alterar_quantidade, name='alterar_quantidade'),
    path('finalizar-compra/', views.finalizar_compra, name='finalizar_compra'),

]

# Adiciona a configuração para servir arquivos de mídia durante o desenvolvimento
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)