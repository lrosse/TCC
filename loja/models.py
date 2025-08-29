
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid

class Produto(models.Model):
    nome = models.CharField(max_length=200)
    descricao = models.TextField()
    preco = models.DecimalField(max_digits=10, decimal_places=2)
    quantidade = models.IntegerField(default=0)  # Campo adicionado
    imagem = models.ImageField(upload_to='produtos/', blank=True, null=True)

    def __str__(self):
        return self.nome
    
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
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE)
    quantidade = models.PositiveIntegerField()
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)

    def subtotal(self):
        return self.quantidade * self.preco_unitario

    def __str__(self):
        return f"{self.quantidade}x {self.produto.nome} no Pedido #{self.pedido.id}"

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
