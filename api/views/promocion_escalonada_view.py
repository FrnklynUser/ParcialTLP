from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from api.models.promocion import Promocion
from api.models.condicion_promocion import CondicionPromocion
from api.models.beneficio_promocion import BeneficioPromocion
from api.models.producto import Producto
from django.utils import timezone

class PromocionEscalonadaView(APIView):
    """
    Endpoint para registrar una promoción de bonificación escalonada por volumen (caso 7).
    Espera un JSON con la estructura:
    {
        "nombre": "Promo AB Bonificación Escalonada",
        "fecha_inicio": "2025-06-01",
        "fecha_fin": "2025-12-31",
        "tipo_promocion": "bonificacion_escalonada",
        "empresa": 1,
        "sucursal": 1,
        "canal_cliente": 1,
        "producto_id": 1,  # ID del producto AB
        "rangos": [
            {"cajas": 6, "bonificacion": 2},
            {"cajas": 18, "bonificacion": 9}
        ]
    }
    """
    def post(self, request):
        data = request.data
        try:
            producto = Producto.objects.get(id=data['producto_id'])
            promocion = Promocion.objects.create(
                nombre=data['nombre'],
                fecha_inicio=data['fecha_inicio'],
                fecha_fin=data['fecha_fin'],
                tipo_promocion=data['tipo_promocion'],
                empresa_id=data['empresa'],
                sucursal_id=data['sucursal'],
                canal_cliente_id=data['canal_cliente']
            )
            for rango in data['rangos']:
                CondicionPromocion.objects.create(
                    promocion=promocion,
                    tipo_condicion='cantidad_escala',
                    valor_min=rango['cajas'],
                    valor_max=None,
                    producto=producto,
                    bonificacion_descuento=True
                )
                BeneficioPromocion.objects.create(
                    promocion=promocion,
                    tipo_beneficio='bonificacion',
                    producto_bonificado=producto,
                    cantidad=rango['bonificacion']
                )
            return Response({'msg': 'Promoción escalonada creada', 'promocion_id': promocion.id}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class PromocionEscalonadaConAdicionalView(APIView):
    """
    Endpoint para registrar una promoción de bonificación escalonada por volumen (caso 8).
    Espera un JSON con la estructura:
    {
        "nombre": "Promo AB Bonificación Escalonada + Adicional",
        "fecha_inicio": "2025-06-01",
        "fecha_fin": "2025-12-31",
        "tipo_promocion": "bonificacion_escalonada_adicional",
        "empresa": 1,
        "sucursal": 1,
        "canal_cliente": 1,
        "producto_id": 1,  # ID del producto AB
        "producto_adicional_id": 2,  # ID del producto C
        "rangos": [
            {"cajas": 6, "bonificacion": 2},
            {"cajas": 18, "bonificacion": 9, "adicional": 2}
        ]
    }
    """
    def post(self, request):
        data = request.data
        try:
            producto = Producto.objects.get(id=data['producto_id'])
            producto_adicional = Producto.objects.get(id=data['producto_adicional_id']) if 'producto_adicional_id' in data else None
            promocion = Promocion.objects.create(
                nombre=data['nombre'],
                fecha_inicio=data['fecha_inicio'],
                fecha_fin=data['fecha_fin'],
                tipo_promocion=data['tipo_promocion'],
                empresa_id=data['empresa'],
                sucursal_id=data['sucursal'],
                canal_cliente_id=data['canal_cliente']
            )
            for rango in data['rangos']:
                CondicionPromocion.objects.create(
                    promocion=promocion,
                    tipo_condicion='cantidad_escala',
                    valor_min=rango['cajas'],
                    valor_max=None,
                    producto=producto,
                    bonificacion_descuento=True
                )
                BeneficioPromocion.objects.create(
                    promocion=promocion,
                    tipo_beneficio='bonificacion',
                    producto_bonificado=producto,
                    cantidad=rango['bonificacion']
                )
                # Si el rango tiene adicional, crear beneficio para producto adicional
                if 'adicional' in rango and producto_adicional:
                    BeneficioPromocion.objects.create(
                        promocion=promocion,
                        tipo_beneficio='bonificacion',
                        producto_bonificado=producto_adicional,
                        cantidad=rango['adicional']
                    )
            return Response({'msg': 'Promoción escalonada con adicional creada', 'promocion_id': promocion.id}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
