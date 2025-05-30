# api/services/promocion_engine.py

from api.models import Promocion, PromocionAplicada, CondicionPromocion, BeneficioPromocion, Producto
from datetime import date

class PromocionEngine:
    """
    Motor principal para la aplicación de promociones a un pedido.
    Orquesta el filtrado, evaluación de condiciones y cálculo de beneficios.
    """
    def __init__(self, pedido, detalles):
        self.pedido = pedido
        self.detalles = detalles  # lista de dicts: [{'producto': id, 'cantidad': x, ...}]
        self.promociones_aplicadas = []
        self.bonificaciones = []

    def aplicar_promociones(self):
        """
        Aplica todas las promociones vigentes y relevantes al pedido.
        Retorna una lista de beneficios aplicados (instancias de PromocionAplicada o dicts).
        """
        promociones = self._filtrar_promociones()
        for promo in promociones:
            for condicion in promo.condiciones.all():
                if condicion.tipo_condicion == 'cantidad' and condicion.producto:
                    cantidad_pedido = sum([
                        d['cantidad'] for d in self.detalles if int(d['producto']) == condicion.producto.id
                    ])
                    if cantidad_pedido >= condicion.valor_min:
                        multiplos = int(cantidad_pedido // condicion.valor_min)
                        for beneficio in promo.beneficios.all():
                            if beneficio.tipo_beneficio == 'bonificacion' and beneficio.producto_bonificado:
                                bonificacion_total = beneficio.cantidad * multiplos
                                self.bonificaciones.append({
                                    'producto_bonificado': beneficio.producto_bonificado.id,
                                    'cantidad': bonificacion_total
                                })
                                PromocionAplicada.objects.create(
                                    pedido=self.pedido,
                                    promocion=promo,
                                    descripcion_resultado=f"Bonificación de {bonificacion_total} {beneficio.producto_bonificado.nombre}"
                                )
                                self.promociones_aplicadas.append(promo)
        return self.bonificaciones

    def _filtrar_promociones(self):
        hoy = date.today()
        sucursal = self.pedido.sucursal
        cliente = self.pedido.cliente
        return Promocion.objects.filter(
            fecha_inicio__lte=hoy,
            fecha_fin__gte=hoy,
            empresa=sucursal.empresa,
            sucursal=sucursal,
            canal_cliente=cliente.canal
        )

    def _cumple_condiciones(self, promo):
        """
        Evalúa si el pedido cumple las condiciones de la promoción.
        Delegar a evaluadores de condición según tipo.
        """
        # TODO: Implementar evaluación de condiciones.
        return False

    def _calcular_beneficio(self, promo):
        """
        Calcula el beneficio (bonificación, descuento, etc.) para la promoción.
        Delegar a calculadores de beneficio según tipo.
        """
        # TODO: Implementar cálculo de beneficio.
        return None

# NOTA: Implementar clases/fábricas para evaluadores de condición y calculadores de beneficio en este módulo o submódulos.
# Ejemplo: CondicionPorProductoEvaluator, BeneficioBonificacionCalculator, etc.
