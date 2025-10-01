
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.timezone import now
import uuid

class Produto(models.Model):
    nome = models.CharField(max_length=200)
    descricao = models.TextField()
    preco = models.DecimalField(max_digits=10, decimal_places=2)
    quantidade = models.IntegerField(default=0)  # estoque atual
    imagem = models.ImageField(upload_to='produtos/', blank=True, null=True)

    # 🔹 Campos de controle de estoque
    minimo_estoque = models.IntegerField(default=5)   # até aqui = vermelho
    ideal_estoque = models.IntegerField(default=10)   # até aqui = amarelo, acima = verde

    # 🔹 Novo campo para ativar/inativar produto
    ativo = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        """
        Regra automática:
        - Se quantidade == 0 → inativa o produto
        - Se quantidade > 0 → ativa o produto (a menos que tenha sido desativado manualmente)
        """
        try:
            qtd = int(self.quantidade) if self.quantidade is not None else 0
        except ValueError:
            qtd = 0

        if qtd <= 0:
            self.ativo = False
        else:
            if self.ativo is not False:
                self.ativo = True

        super().save(*args, **kwargs)

        def _str_(self):
            return self.nome

    def __str__(self):
        return self.nome


class CustoProduto(models.Model):
    produto = models.OneToOneField("Produto", on_delete=models.CASCADE, related_name="custo_info")
    custo = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.produto.nome} - Custo: R$ {self.custo}"

class Carrinho(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE)
    valor_total = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    data_criacao = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Carrinho de {self.usuario.username}"

    def calcular_total(self):
        total = sum(item.subtotal() for item in self.itemcarrinho_set.all())
        self.valor_total = total
        self.save()
        return total

    def total(self):
        return self.calcular_total()
class ItemCarrinho(models.Model):
    carrinho = models.ForeignKey(Carrinho, on_delete=models.CASCADE)
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE)
    quantidade = models.PositiveIntegerField(default=1)
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    data_adicionado = models.DateTimeField(auto_now_add=True)

    def subtotal(self):
        return self.quantidade * self.preco_unitario

    def __str__(self):
        return f"{self.produto.nome} x {self.quantidade}"
class EntradaEstoque(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE)
    quantidade_adicionada = models.PositiveIntegerField()
    data = models.DateTimeField(default=timezone.now)
    observacao = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.quantidade_adicionada} un. para {self.produto.nome} em {self.data.strftime('%d/%m/%Y %H:%M')}"
    
class MovimentacaoEstoque(models.Model):
    TIPO_CHOICES = (
        ('entrada', 'Entrada de Estoque'),
        ('ajuste', 'Ajuste Manual'),
    )

    produto = models.ForeignKey(Produto, on_delete=models.CASCADE)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    quantidade = models.IntegerField()
    estoque_final = models.IntegerField()
    data = models.DateTimeField(auto_now_add=True)
    observacao = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"[{self.get_tipo_display()}] {self.produto.nome} - {self.quantidade} un. - {self.data.strftime('%d/%m/%Y %H:%M')}"
    
# ------------------------------
# Model para armazenar o pedido
# ------------------------------
class Pedido(models.Model):
    STATUS_CHOICES = [
        ('Pendente', 'Pendente'),
        ('Pago', 'Pago'),
        ('Cancelado', 'Cancelado'),
    ]

    cliente = models.ForeignKey(User, on_delete=models.CASCADE)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pendente')
    data_criacao = models.DateTimeField(auto_now_add=True)

    nome_cliente = models.CharField(max_length=100)
    endereco_entrega = models.TextField()

    numero_pedido = models.CharField(max_length=30, unique=True, editable=False, blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.numero_pedido:
            agora = timezone.now()
            prefixo = agora.strftime("%Y%m")  # 202508
            codigo_unico = str(uuid.uuid4()).replace('-', '')[:8].upper()
            # Resultado: 202508-A1B2C3D4 (impossível ter conflito)
            self.numero_pedido = f"{prefixo}-{codigo_unico}"
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Pedido {self.numero_pedido or self.id} - {self.cliente.username}"
# ----------------------------------------------------
# Model para armazenar cada item que compõe o pedido
# ----------------------------------------------------
class PedidoItem(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey(Produto, on_delete=models.SET_NULL, null=True, blank=True)  
    # 🔹 mantém referência ao produto, mas permite null se ele for excluído

    # 🔹 Campos congelados no momento do pedido
    nome_produto = models.CharField(max_length=200)  
    quantidade = models.PositiveIntegerField()
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    custo_unitario = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def subtotal(self):
        return self.quantidade * self.preco_unitario

    def __str__(self):
        return f"{self.quantidade}x {self.nome_produto} no Pedido #{self.pedido.id}"
    
class HistoricoCusto(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name="historico_custos")
    custo_antigo = models.DecimalField(max_digits=10, decimal_places=2)
    custo_novo = models.DecimalField(max_digits=10, decimal_places=2)
    data = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"[{self.produto.nome}] {self.custo_antigo} → {self.custo_novo} em {self.data.strftime('%d/%m/%Y %H:%M')}"

# ------------------------------
# Model para armazenar feedbacks
# ------------------------------
class Feedback(models.Model):
    NOTA_CHOICES = [
        (1, "1 - Péssimo"),
        (2, "2 - Ruim"),
        (3, "3 - Regular"),
        (4, "4 - Bom"),
        (5, "5 - Excelente"),
    ]

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name="feedbacks")
    produto = models.ForeignKey("Produto", on_delete=models.CASCADE, related_name="feedbacks", null=True, blank=True)
    pedido = models.ForeignKey("Pedido", on_delete=models.CASCADE, related_name="feedbacks", null=True, blank=True)

    nota = models.PositiveSmallIntegerField(choices=NOTA_CHOICES)
    comentario = models.TextField(blank=True, null=True)
    visivel = models.BooleanField(default=True)  # 👈 novo campo

    data_criacao = models.DateTimeField(default=timezone.now)
    data_atualizacao = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.usuario.username} - {self.nota}⭐ ({'visível' if self.visivel else 'oculto'})"


class LancamentoFinanceiro(models.Model):
    TIPO_CHOICES = [
        ('receita', 'Receita'),
        ('despesa', 'Despesa'),
    ]

    categoria = models.CharField(max_length=100)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    data = models.DateField(default=timezone.now)
    descricao = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.categoria} - R$ {self.valor}"

class Despesa(models.Model):
    TIPOS = [
        ("Fixo", "Fixo"),
        ("Variável", "Variável"),
    ]

    categoria = models.CharField(max_length=100)  # Ex: Aluguel, Marketing
    tipo = models.CharField(max_length=10, choices=TIPOS)
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    data = models.DateField(default=now)  # data inicial
    descricao = models.TextField(blank=True, null=True)

    fornecedor = models.CharField(max_length=150, blank=True, null=True)  # 🔹 novo campo
    parcelas = models.PositiveIntegerField(default=1)  # 🔹 número de parcelas

    def __str__(self):
        return f"{self.categoria} - R$ {self.valor:.2f} ({self.fornecedor or 'Sem fornecedor'})"
