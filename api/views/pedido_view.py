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
        # Se activa el filtro de fechas para cumplir la regla de vigencia
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
        # --- Lógica adicional para CASO 2: Bonificación por importe, línea y marca, solo mayoristas ---
        for promo in promociones:
            for condicion in promo.condiciones.all():
                if condicion.tipo_condicion == 'importe' and condicion.linea_producto and condicion.bonificacion_descuento:
                    # Solo para canal mayorista
                    if cliente.canal.nombre.upper() == 'MAYORISTA':
                        # Sumar importe de productos de la línea y marca BOLÍVAR
                        importe = 0
                        for d in detalles:
                            prod = Producto.objects.get(id=d['producto'])
                            if prod.linea_id == condicion.linea_producto.id and prod.marca.upper() == 'BOLÍVAR':
                                importe += d['cantidad'] * d['precio_unitario']
                        if importe >= condicion.valor_min:
                            multiplos = int(importe // condicion.valor_min)
                            # Bonificaciones fijas del caso 2
                            # 2 unidades de 400051B y 1 unidad de 400536B por cada S/100
                            productos_bonificados = [
                                {'codigo': '400051B', 'cantidad': 2},
                                {'codigo': '400536B', 'cantidad': 1}
                            ]
                            for pb in productos_bonificados:
                                try:
                                    prod_bonif = Producto.objects.get(codigo=pb['codigo'])
                                    bonificacion_total = pb['cantidad'] * multiplos
                                    if bonificacion_total > 0:
                                        bonificaciones.append({
                                            'producto_bonificado_id': prod_bonif.id,
                                            'producto_bonificado_nombre': prod_bonif.nombre,
                                            'cantidad': bonificacion_total,
                                            'promocion': promo.nombre
                                        })
                                        PromocionAplicada.objects.create(
                                            pedido=pedido,
                                            promocion=promo,
                                            descripcion_resultado=f"Bonificación de {bonificacion_total} {prod_bonif.nombre} por promoción '{promo.nombre}' (CASO 2)"
                                        )
                                except Producto.DoesNotExist:
                                    continue
        # --- Lógica adicional para CASO 3: Descuento por volumen en producto BEL001 solo COBERTURA ---
        for promo in promociones:
            for condicion in promo.condiciones.all():
                if (
                    condicion.tipo_condicion == 'cantidad' and
                    condicion.producto and
                    condicion.producto.codigo == 'BEL001' and
                    condicion.bonificacion_descuento
                ):
                    # Solo para canal COBERTURA
                    if cliente.canal.nombre.upper() == 'COBERTURA':
                        cantidad_pedido = sum([
                            d['cantidad'] for d in detalles
                            if Producto.objects.get(id=d['producto']).codigo == 'BEL001'
                        ])
                        if cantidad_pedido > 60:  # Más de 5 cajas (60 unidades)
                            for beneficio in promo.beneficios.all():
                                if beneficio.tipo_beneficio == 'descuento' and beneficio.porcentaje_descuento:
                                    descuento = 0
                                    # Solo se descuenta sobre el subtotal de BEL001
                                    for d in detalles:
                                        prod = Producto.objects.get(id=d['producto'])
                                        if prod.codigo == 'BEL001':
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
                                        descripcion_resultado=f"Descuento del {beneficio.porcentaje_descuento}% por compra de más de 60 unidades de {condicion.producto.nombre} (CASO 3)"
                                    )
        # --- Lógica adicional para CASO 4: Descuento escalonado por volumen para GLO01 (LECHE GLORIA T/PACK LIGHTx1lt) ---
        for promo in Promocion.objects.filter(
            fecha_inicio__lte=hoy,
            fecha_fin__gte=hoy,
            empresa=sucursal.empresa,
            sucursal=sucursal,
            tipo_promocion='descuento',
        ):
            for condicion in promo.condiciones.all():
                if (
                    condicion.tipo_condicion == 'cantidad' and
                    condicion.producto and
                    condicion.producto.codigo == 'GLO01' and
                    condicion.bonificacion_descuento
                ):
                    cantidad_glo01 = sum([
                        d['cantidad'] for d in detalles
                        if Producto.objects.get(id=d['producto']).codigo == 'GLO01'
                    ])
                    if cantidad_glo01 >= condicion.valor_min and (
                        condicion.valor_max is None or cantidad_glo01 <= condicion.valor_max
                    ):
                        for beneficio in promo.beneficios.all():
                            if beneficio.tipo_beneficio == 'descuento' and beneficio.porcentaje_descuento:
                                descuento = 0
                                for d in detalles:
                                    prod = Producto.objects.get(id=d['producto'])
                                    if prod.codigo == 'GLO01':
                                        descuento += d['cantidad'] * d['precio_unitario'] * (beneficio.porcentaje_descuento / 100)
                                total_monto -= descuento
                                pedido.total_monto = total_monto
                                pedido.save()
                                bonificaciones.append({
                                    'descuento': f"{beneficio.porcentaje_descuento}%",
                                    'producto': condicion.producto.nombre,
                                    'cantidad': cantidad_glo01,
                                    'monto_descuento': round(descuento, 2),
                                    'promocion': promo.nombre
                                })
                                PromocionAplicada.objects.create(
                                    pedido=pedido,
                                    promocion=promo,
                                    descripcion_resultado=f"Descuento del {beneficio.porcentaje_descuento}% por compra de {cantidad_glo01} unidades de {condicion.producto.nombre} (CASO 4)"
                                )
        # --- Lógica adicional para CASO 5: Descuento 5% por S/300+ en SALSAS/SILLAO solo MAYORISTA ---
        for promo in promociones:
            for condicion in promo.condiciones.all():
                if (
                    condicion.tipo_condicion == 'importe' and
                    condicion.linea_producto and
                    condicion.linea_producto.nombre.upper() in ['SALSAS', 'SILLAO'] and
                    condicion.bonificacion_descuento
                ):
                    # Solo para canal MAYORISTA
                    if cliente.canal.nombre.upper() == 'MAYORISTA':
                        importe = 0
                        for d in detalles:
                            prod = Producto.objects.get(id=d['producto'])
                            if prod.linea and prod.linea.nombre.upper() in ['SALSAS', 'SILLAO']:
                                importe += d['cantidad'] * d['precio_unitario']
                        if importe >= 300:
                            for beneficio in promo.beneficios.all():
                                if beneficio.tipo_beneficio == 'descuento' and beneficio.porcentaje_descuento:
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
                                        descripcion_resultado=f"Descuento del {beneficio.porcentaje_descuento}% por compra de S/300+ en línea {condicion.linea_producto.nombre} (CASO 5)"
                                    )
        return Response({
            'pedido_id': pedido.id,
            'bonificaciones': bonificaciones
        }, status=status.HTTP_201_CREATED)