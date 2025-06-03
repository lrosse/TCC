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
    
    # Rotas para carrinho
    path('carrinho/adicionar/<int:produto_id>/', views.adicionar_ao_carrinho, name='adicionar_ao_carrinho'),
    path('carrinho/', views.ver_carrinho, name='ver_carrinho'),
    path('carrinho/remover/<int:item_id>/', views.remover_do_carrinho, name='remover_do_carrinho'),
    path('carrinho/alterar/<int:item_id>/', views.alterar_quantidade, name='alterar_quantidade'),
]

# Adiciona a configuração para servir arquivos de mídia durante o desenvolvimento
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)