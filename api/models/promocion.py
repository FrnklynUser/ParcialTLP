from django.db import models
from .empresa import Empresa
from .sucursal import Sucursal
from .canal_cliente import CanalCliente

class Promocion(models.Model):
    nombre = models.CharField(max_length=255)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    tipo_promocion = models.CharField(max_length=50)
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='promociones')
    sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name='promociones')
    canal_cliente = models.ForeignKey(CanalCliente, on_delete=models.CASCADE, related_name='promociones')

    class Meta:
        db_table = 'promocion'
