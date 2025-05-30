# api/services/promocion_engine.py

from api.models import Promocion, PromocionAplicada, CondicionPromocion, BeneficioPromocion, Producto, LineaProducto
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
                self._calcular_beneficio(promo, condicion)
        return self.bonificaciones

    def _calcular_beneficio(self, promo, condicion):
        """
        Calcula el beneficio (bonificación, descuento, etc.) para la promoción.
        Delegar a calculadores de beneficio según tipo.
        """
        # CASO 1: Bonificación por cantidad de producto
        bonificacion_aplicada = False
        if condicion.tipo_condicion == 'cantidad' and condicion.producto:
            cantidad_pedido = sum([
                d['cantidad'] for d in self.detalles if int(d['producto']) == condicion.producto.id
            ])
            if cantidad_pedido >= condicion.valor_min:
                multiplos = int(cantidad_pedido // condicion.valor_min) if not condicion.valor_max else 1
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
                        bonificacion_aplicada = True
                    elif beneficio.tipo_beneficio == 'descuento' and beneficio.porcentaje_descuento:
                        # CASO 3 y CASO 4: Descuento por cantidad (incluye escalas)
                        if (condicion.valor_max is None and cantidad_pedido >= condicion.valor_min) or \
                           (condicion.valor_max is not None and condicion.valor_min <= cantidad_pedido <= condicion.valor_max):
                            monto_producto = sum([
                                d['cantidad'] * d.get('precio_unitario', 0)
                                for d in self.detalles if int(d['producto']) == condicion.producto.id
                            ])
                            descuento = monto_producto * (beneficio.porcentaje_descuento / 100)
                            self.bonificaciones.append({
                                'producto_descuento': condicion.producto.id,
                                'porcentaje_descuento': beneficio.porcentaje_descuento,
                                'monto_descuento': round(descuento, 2)
                            })
                            PromocionAplicada.objects.create(
                                pedido=self.pedido,
                                promocion=promo,
                                descripcion_resultado=f"Descuento del {beneficio.porcentaje_descuento}% sobre {condicion.producto.nombre} por volumen: S/{round(descuento,2)}"
                            )
                            self.promociones_aplicadas.append(promo)
        # CASO 2 y 5: Bonificación o descuento por importe en línea y marca
        elif condicion.tipo_condicion == 'importe' and condicion.linea_producto:
            importe = 0
            productos_en_linea = []
            for d in self.detalles:
                try:
                    producto = Producto.objects.get(id=d['producto'])
                except Producto.DoesNotExist:
                    continue
                if producto.linea_id == condicion.linea_producto.id:
                    productos_en_linea.append(producto.id)
                    # Si la condición requiere marca, filtrar por marca
                    if hasattr(condicion, 'marca') and condicion.marca:
                        if producto.marca != condicion.marca:
                            continue
                    importe += d['cantidad'] * d.get('precio_unitario', 0)
            # Debug: mostrar productos considerados y el importe
            print(f"[DEBUG] Productos en línea {condicion.linea_producto.id}: {productos_en_linea}, Importe total: {importe}")
            if importe >= condicion.valor_min:
                multiplos = int(importe // condicion.valor_min) if not condicion.valor_max else 1
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
                            descripcion_resultado=f"Bonificación de {bonificacion_total} {beneficio.producto_bonificado.nombre} por importe"
                        )
                        self.promociones_aplicadas.append(promo)
                    elif beneficio.tipo_beneficio == 'descuento' and beneficio.porcentaje_descuento:
                        # CASO 5: Descuento por importe en línea
                        if (condicion.valor_max is None and importe >= condicion.valor_min) or \
                           (condicion.valor_max is not None and condicion.valor_min <= importe <= condicion.valor_max):
                            descuento = importe * (beneficio.porcentaje_descuento / 100)
                            self.bonificaciones.append({
                                'linea_descuento': condicion.linea_producto.id,
                                'porcentaje_descuento': beneficio.porcentaje_descuento,
                                'monto_descuento': round(descuento, 2)
                            })
                            PromocionAplicada.objects.create(
                                pedido=self.pedido,
                                promocion=promo,
                                descripcion_resultado=f"Descuento del {beneficio.porcentaje_descuento}% sobre línea {condicion.linea_producto.nombre} por importe: S/{round(descuento,2)}"
                            )
                            self.promociones_aplicadas.append(promo)
            else:
                print(f"[DEBUG] No se alcanza el importe mínimo para la línea {condicion.linea_producto.id}. Importe: {importe}, Mínimo: {condicion.valor_min}")
        # CASO 6: Descuento escalonado por importe en producto específico (rango)
        elif condicion.tipo_condicion == 'importe' and condicion.producto:
            # Solo ejecutar la lógica una vez por producto en el pedido
            if not hasattr(self, '_productos_descuento_aplicados'):
                self._productos_descuento_aplicados = set()
            if condicion.producto.id in self._productos_descuento_aplicados:
                return
            importe_producto = 0
            for d in self.detalles:
                if int(d['producto']) == condicion.producto.id:
                    importe_producto += d['cantidad'] * d.get('precio_unitario', 0)
            condiciones_producto = [c for c in promo.condiciones.all() if c.tipo_condicion == 'importe' and c.producto and c.producto.id == condicion.producto.id]
            mejor_condicion = None
            for c in condiciones_producto:
                if (c.valor_max is not None and c.valor_min <= importe_producto <= c.valor_max) or (c.valor_max is None and importe_producto >= c.valor_min):
                    if mejor_condicion is None or c.valor_min > mejor_condicion.valor_min:
                        mejor_condicion = c
            if mejor_condicion:
                beneficio_escala = None
                for beneficio in promo.beneficios.all():
                    if beneficio.tipo_beneficio == 'descuento' and beneficio.porcentaje_descuento:
                        if (
                            (mejor_condicion.valor_min == 500 and mejor_condicion.valor_max == 1499 and beneficio.porcentaje_descuento == 2) or
                            (mejor_condicion.valor_min == 1500 and mejor_condicion.valor_max == 4000 and beneficio.porcentaje_descuento == 4) or
                            (mejor_condicion.valor_min == 4001 and mejor_condicion.valor_max is None and beneficio.porcentaje_descuento == 5)
                        ):
                            beneficio_escala = beneficio
                            break
                if beneficio_escala:
                    descuento = importe_producto * (beneficio_escala.porcentaje_descuento / 100)
                    self.bonificaciones.append({
                        'producto_descuento': mejor_condicion.producto.id,
                        'porcentaje_descuento': beneficio_escala.porcentaje_descuento,
                        'monto_descuento': round(descuento, 2)
                    })
                    PromocionAplicada.objects.create(
                        pedido=self.pedido,
                        promocion=promo,
                        descripcion_resultado=f"Descuento del {beneficio_escala.porcentaje_descuento}% sobre {mejor_condicion.producto.nombre} por importe: S/{round(descuento,2)}"
                    )
                    self.promociones_aplicadas.append(promo)
                    self._productos_descuento_aplicados.add(condicion.producto.id)
            else:
                print(f"[DEBUG] No se alcanza el importe mínimo para el producto {condicion.producto.id}. Importe: {importe_producto}, Mínimo: {condicion.valor_min}")
        # CASO 7: Bonificación escalonada por volumen (rango) para producto específico
        # Ejemplo: Producto AB, 6 cajas (36 unidades) = 2 unidades bonificadas, 18 cajas (108 unidades) o más = 9 unidades bonificadas
        # Solo ejecutar si NO se aplicó bonificación estándar arriba
        if not bonificacion_aplicada and condicion.tipo_condicion == 'cantidad' and condicion.producto:
            producto_ab_codigo = 'AB'  # Cambia esto si el identificador es diferente
            try:
                producto_obj = Producto.objects.get(id=condicion.producto.id)
            except Producto.DoesNotExist:
                producto_obj = None
            if producto_obj and producto_obj.codigo == producto_ab_codigo:
                cantidad_pedido = sum([
                    d['cantidad'] for d in self.detalles if int(d['producto']) == condicion.producto.id
                ])
                # Asumimos que cada caja tiene 6 unidades
                unidades_por_caja = 6
                cajas_compradas = cantidad_pedido / unidades_por_caja
                bonificacion = 0
                if cajas_compradas >= 18:
                    bonificacion = 9
                elif cajas_compradas >= 6:
                    bonificacion = 2
                if bonificacion > 0:
                    self.bonificaciones.append({
                        'producto_bonificado': condicion.producto.id,
                        'cantidad': bonificacion
                    })
                    PromocionAplicada.objects.create(
                        pedido=self.pedido,
                        promocion=promo,
                        descripcion_resultado=f"Bonificación escalonada: {bonificacion} unidades de {producto_obj.nombre} por compra de {int(cajas_compradas)} cajas"
                    )
                    self.promociones_aplicadas.append(promo)
                    return

    def _filtrar_promociones(self):
        hoy = date.today()
        sucursal = self.pedido.sucursal
        cliente = self.pedido.cliente
        # Filtrar solo promociones del canal correspondiente
        promociones = Promocion.objects.filter(
            fecha_inicio__lte=hoy,
            fecha_fin__gte=hoy,
            empresa=sucursal.empresa,
            sucursal=sucursal,
            canal_cliente=cliente.canal
        )
        # Si la promoción es para canal MAYORISTA, solo aplicar si el cliente es mayorista
        promociones_filtradas = []
        for promo in promociones:
            if promo.canal_cliente.nombre.upper() == 'MAYORISTA':
                if cliente.canal.nombre.upper() == 'MAYORISTA':
                    promociones_filtradas.append(promo)
            else:
                promociones_filtradas.append(promo)
        return promociones_filtradas

    def _cumple_condiciones(self, promo):
        """
        Evalúa si el pedido cumple las condiciones de la promoción.
        Delegar a evaluadores de condición según tipo.
        """
        # TODO: Implementar evaluación de condiciones.
        return False

    # NOTA: Implementar clases/fábricas para evaluadores de condición y calculadores de beneficio en este módulo o submódulos.
    # Ejemplo: CondicionPorProductoEvaluator, BeneficioBonificacionCalculator, etc.
