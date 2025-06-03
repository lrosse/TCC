
from django.db import models
from django.contrib.auth.models import User

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