from django.db import models
from .cliente import Cliente

class Pedido(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='pedidos')
    fecha = models.DateTimeField(auto_now_add=True)
    total_monto = models.FloatField()

    class Meta:
        db_table = 'pedido'
