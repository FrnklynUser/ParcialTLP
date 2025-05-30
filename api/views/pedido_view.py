from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from api.models import Pedido, PedidoDetalle, Cliente, Promocion, CondicionPromocion, BeneficioPromocion, PromocionAplicada, Producto, Sucursal
from django.db import transaction
from datetime import date
from django.core.exceptions import ObjectDoesNotExist

class PedidoViewSet(viewsets.ViewSet):
    @transaction.atomic
    def create(self, request):
        try:
            cliente_id = request.data.get('cliente')
            sucursal_id = request.data.get('sucursal')
            detalles = request.data.get('detalles', [])
            cliente = Cliente.objects.get(id=cliente_id)
            sucursal = Sucursal.objects.get(id=sucursal_id)
        except ObjectDoesNotExist:
            return Response({'error': 'El cliente o la sucursal no existe.'}, status=400)
        pedido = Pedido.objects.create(cliente=cliente, sucursal=sucursal, total_monto=0)
        total_monto = 0
        for d in detalles:
            producto = Producto.objects.get(id=d['producto'])
            cantidad = d['cantidad']
            precio_unitario = d['precio_unitario']
            PedidoDetalle.objects.create(pedido=pedido, producto=producto, cantidad=cantidad, precio_unitario=precio_unitario)
            total_monto += cantidad * precio_unitario
        pedido.total_monto = total_monto
        pedido.save()

        hoy = date.today()
        promociones = Promocion.objects.filter(
            fecha_inicio__lte=hoy,
            fecha_fin__gte=hoy,
            empresa=sucursal.empresa,
            sucursal=sucursal,
            canal_cliente=cliente.canal
        )
        bonificaciones = []
        for promo in promociones:
            for condicion in promo.condiciones.all():
                if condicion.tipo_condicion == 'cantidad' and condicion.producto:
                    cantidad_pedido = sum([d['cantidad'] for d in detalles if d['producto'] == condicion.producto.id])
                    if cantidad_pedido >= condicion.valor_min:
                        multiplos = int(cantidad_pedido // condicion.valor_min)
                        for beneficio in promo.beneficios.all():
                            if beneficio.tipo_beneficio == 'bonificacion' and beneficio.producto_bonificado:
                                bonificacion_total = beneficio.cantidad * multiplos
                                bonificaciones.append({
                                    'producto_bonificado': beneficio.producto_bonificado.id,
                                    'cantidad': bonificacion_total
                                })
                                PromocionAplicada.objects.create(
                                    pedido=pedido,
                                    promocion=promo,
                                    descripcion_resultado=f"Bonificación de {bonificacion_total} {beneficio.producto_bonificado.nombre}"
                                )
        return Response({
            'pedido_id': pedido.id,
            'bonificaciones': bonificaciones
        }, status=status.HTTP_201_CREATED)