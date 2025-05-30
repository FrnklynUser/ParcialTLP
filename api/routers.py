from rest_framework.routers import DefaultRouter
from api.views.empresa_view import EmpresaViewSet
from api.views.sucursal_view import SucursalViewSet

router = DefaultRouter()
router.register(r'empresas', EmpresaViewSet)
router.register(r'sucursales', SucursalViewSet)

urlpatterns = router.urls 