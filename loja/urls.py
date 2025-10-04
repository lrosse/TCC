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
    path('produto/<int:produto_id>/', views.produto_detalhe, name='produto_detalhe'),
    path("buscar-produtos/", views.buscar_produtos, name="buscar_produtos"),

    # Rotas para estoque
    path('produtos/entrada-estoque/', views.entrada_estoque, name='entrada_estoque'),
    path('produtos/ajuste-estoque/', views.ajuste_estoque, name='ajuste_estoque'),
    path('produtos/historico-estoque/', views.historico_estoque, name='historico_estoque'),
    path("produtos/alterar-status/", views.alterar_status_produtos, name="alterar_status_produtos"),

    # Rotas para carrinho
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


    # 🔹 NOVAS ROTAS DE FINANCEIRO (separadas)
        # Financeiro (separado)
    path("gestao/financeiro/resumo/", views_gestao.financeiro_resumo, name="financeiro_resumo"),
    path("gestao/financeiro/produtos/", views_gestao.financeiro_produtos, name="financeiro_produtos"),
    path("gestao/financeiro/pedidos/", views_gestao.financeiro_pedidos, name="financeiro_pedidos"),
    path("gestao/historico-custo/", views_gestao.historico_custo, name="historico_custo"),
    
    # Despesas (separado)
    path("gestao/despesas/", views_gestao.gestao_despesas, name="gestao_despesas"),
    path("gestao/despesas/nova/", views_gestao.criar_despesa, name="criar_despesa"),
    path("gestao/despesas/editar/<int:pk>/", views_gestao.editar_despesa, name="editar_despesa"),
    path("gestao/despesas/excluir/<int:pk>/", views_gestao.excluir_despesa, name="excluir_despesa"),
    path("gestao/despesas/<int:pk>/detalhes/", views_gestao.detalhes_despesa, name="detalhes_despesa"),

    #relatorio
    path("gestao/relatorio_avancado/", views_gestao.relatorio_avancado, name="relatorio_avancado"),

    #caminho dos relatorios avanacado
    path("gestao/relatorios/produtos/", views_gestao.relatorio_produtos, name="relatorio_produtos"),
    path("gestao/relatorios/pedidos/", views_gestao.relatorio_pedidos, name="relatorio_pedidos"),
    path("gestao/relatorios/estoque/", views_gestao.relatorio_estoque, name="relatorio_estoque"),
    path("gestao/relatorios/financeiro/", views_gestao.relatorio_financeiro, name="relatorio_financeiro"),
    path("gestao/relatorios/feedbacks/", views_gestao.relatorio_feedbacks, name="relatorio_feedbacks"),

    #caminho para pdf
    path("gestao/relatorios/produtos/pdf/", views_gestao.relatorio_produtos_pdf, name="relatorio_produtos_pdf"),
    path("gestao/relatorios/pedidos/pdf/", views_gestao.relatorio_pedidos_pdf, name="relatorio_pedidos_pdf"),
    path("gestao/relatorios/estoque/pdf/", views_gestao.relatorio_estoque_pdf, name="relatorio_estoque_pdf"),
    path("gestao/relatorios/financeiro/pdf/", views_gestao.relatorio_financeiro_pdf, name="relatorio_financeiro_pdf"),
    path("gestao/relatorios/feedbacks/pdf/", views_gestao.relatorio_feedbacks_pdf, name="relatorio_feedbacks_pdf"),
]

# Adiciona a configuração para servir arquivos de mídia durante o desenvolvimento
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
