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

        # Motor de promociones completamente dinámico
        bonificaciones = []
        hoy = date.today()
        promociones = Promocion.objects.filter(
            fecha_inicio__lte=hoy,
            fecha_fin__gte=hoy,
            empresa=sucursal.empresa,
            sucursal=sucursal,
            canal_cliente=cliente.canal
        )
        for promo in promociones:
            for condicion in promo.condiciones.all():
                # --- Condición por cantidad de producto ---
                if condicion.tipo_condicion == 'cantidad' and condicion.producto:
                    cantidad_pedido = sum([
                        d['cantidad'] for d in detalles if d['producto'] == condicion.producto.id
                    ])
                    if cantidad_pedido >= condicion.valor_min and (
                        condicion.valor_max is None or cantidad_pedido <= condicion.valor_max
                    ):
                        multiplos = int(cantidad_pedido // condicion.valor_min)
                        for beneficio in promo.beneficios.all():
                            if beneficio.tipo_beneficio == 'bonificacion' and beneficio.producto_bonificado:
                                bonificacion_total = beneficio.cantidad * multiplos
                                if bonificacion_total > 0:
                                    bonificaciones.append({
                                        'producto_bonificado_id': beneficio.producto_bonificado.id,
                                        'producto_bonificado_nombre': beneficio.producto_bonificado.nombre,
                                        'cantidad': bonificacion_total,
                                        'promocion': promo.nombre
                                    })
                                    PromocionAplicada.objects.create(
                                        pedido=pedido,
                                        promocion=promo,
                                        descripcion_resultado=f"Bonificación de {bonificacion_total} {beneficio.producto_bonificado.nombre} por promoción '{promo.nombre}'"
                                    )
                            elif beneficio.tipo_beneficio == 'descuento' and beneficio.porcentaje_descuento:
                                descuento = 0
                                for d in detalles:
                                    if d['producto'] == condicion.producto.id:
                                        descuento += d['cantidad'] * d['precio_unitario'] * (beneficio.porcentaje_descuento / 100)
                                total_monto -= descuento
                                pedido.total_monto = total_monto
                                pedido.save()
                                bonificaciones.append({
                                    'descuento': f"{beneficio.porcentaje_descuento}%",
                                    'producto': condicion.producto.nombre,
                                    'cantidad': cantidad_pedido,
                                    'monto_descuento': round(descuento, 2),
                                    'promocion': promo.nombre
                                })
                                PromocionAplicada.objects.create(
                                    pedido=pedido,
                                    promocion=promo,
                                    descripcion_resultado=f"Descuento del {beneficio.porcentaje_descuento}% por compra de {cantidad_pedido} unidades de {condicion.producto.nombre} (Promo: {promo.nombre})"
                                )
                # --- Condición por importe de línea/marca ---
                elif condicion.tipo_condicion == 'importe' and condicion.linea_producto:
                    importe = 0
                    for d in detalles:
                        prod = Producto.objects.get(id=d['producto'])
                        if prod.linea_id == condicion.linea_producto.id:
                            if not condicion.producto or prod.id == condicion.producto.id:
                                importe += d['cantidad'] * d['precio_unitario']
                    if importe >= condicion.valor_min and (
                        condicion.valor_max is None or importe <= condicion.valor_max
                    ):
                        multiplos = int(importe // condicion.valor_min)
                        for beneficio in promo.beneficios.all():
                            if beneficio.tipo_beneficio == 'bonificacion' and beneficio.producto_bonificado:
                                bonificacion_total = beneficio.cantidad * multiplos
                                if bonificacion_total > 0:
                                    bonificaciones.append({
                                        'producto_bonificado_id': beneficio.producto_bonificado.id,
                                        'producto_bonificado_nombre': beneficio.producto_bonificado.nombre,
                                        'cantidad': bonificacion_total,
                                        'promocion': promo.nombre
                                    })
                                    PromocionAplicada.objects.create(
                                        pedido=pedido,
                                        promocion=promo,
                                        descripcion_resultado=f"Bonificación de {bonificacion_total} {beneficio.producto_bonificado.nombre} por promoción '{promo.nombre}'"
                                    )
                            elif beneficio.tipo_beneficio == 'descuento' and beneficio.porcentaje_descuento:
                                descuento = importe * (beneficio.porcentaje_descuento / 100)
                                total_monto -= descuento
                                pedido.total_monto = total_monto
                                pedido.save()
                                bonificaciones.append({
                                    'descuento': f"{beneficio.porcentaje_descuento}%",
                                    'linea': condicion.linea_producto.nombre,
                                    'importe': round(importe, 2),
                                    'monto_descuento': round(descuento, 2),
                                    'promocion': promo.nombre
                                })
                                PromocionAplicada.objects.create(
                                    pedido=pedido,
                                    promocion=promo,
                                    descripcion_resultado=f"Descuento del {beneficio.porcentaje_descuento}% por compra de S/{importe} en línea {condicion.linea_producto.nombre} (Promo: {promo.nombre})"
                                )
        # Actualizar el monto final del pedido
        pedido.total_monto = total_monto
        pedido.save()
        return Response({
            'pedido_id': pedido.id,
            'bonificaciones': bonificaciones
        }, status=status.HTTP_201_CREATED)