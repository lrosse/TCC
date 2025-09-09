from django.urls import path
from . import views, views_gestao
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
    path("buscar-produtos/", views.buscar_produtos, name="buscar_produtos"),


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

    # Página de pedidos
    path('pedidos/', views.pedidos, name='pedidos'),
    path('pedidos/<int:pedido_id>/', views.detalhes_pedido, name='detalhes_pedido'),
    path('pedidos/atualizar-status/<int:pedido_id>/', views.atualizar_status_pedido, name='atualizar_status_pedido'),
    path('pedidos/atualizar-status-lote/', views.atualizar_status_pedidos_lote, name='atualizar_status_pedidos_lote'),
    
    # Página de Relatórios (apenas staff/admin)
    path('relatorios/', views.relatorios, name='relatorios'),

    # Página de Meus Pedidos (usuário comum)
    path('meus_pedidos/', views.meus_pedidos, name='meus_pedidos'),
    path('meus_pedidos/<int:pedido_id>/', views.detalhes_pedido_cliente, name='detalhes_pedido_cliente'),
    
    # Página de Feedbacks
    path('produto/<int:produto_id>/feedback/', views.adicionar_feedback, name='adicionar_feedback'),
    path('feedbacks/', views.listar_feedbacks, name='listar_feedbacks'),
    path('feedbacks/<int:feedback_id>/', views.detalhes_feedback, name='detalhes_feedback'),
    path('feedbacks/atualizar-lote/', views.atualizar_feedbacks_lote, name='atualizar_feedbacks_lote'),

    # API para adicionar ao carrinho via AJAX
    path("carrinho/adicionar/<int:produto_id>/", views.adicionar_carrinho, name="adicionar_carrinho"),

    # Gestão
    path("gestao/", views_gestao.gestao_index, name="gestao_index"),
    path("gestao/estoque/", views_gestao.gestao_estoque, name="gestao_estoque"),
    path("gestao/financeiro/", views_gestao.financeiro, name="financeiro"),
    path("gestao/financeiro/adicionar/", views_gestao.adicionar_lancamento, name="adicionar_lancamento"),
    path("gestao/financeiro/exportar/csv/", views_gestao.exportar_financeiro_csv, name="exportar_financeiro_csv"),
    path("gestao/financeiro/exportar/pdf/", views_gestao.exportar_financeiro_pdf, name="exportar_financeiro_pdf"),

    path("gestao/despesa/<int:pk>/editar/", views_gestao.editar_despesa, name="editar_despesa"),
    path("gestao/despesa/<int:pk>/excluir/", views_gestao.excluir_despesa, name="excluir_despesa"),

        


]

# Adiciona a configuração para servir arquivos de mídia durante o desenvolvimento
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)