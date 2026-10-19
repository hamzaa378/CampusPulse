from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from monitor import views

router = DefaultRouter()
router.register(r"sensors", views.SensorViewSet, basename="sensors")
router.register(r"rules", views.RuleViewSet, basename="rules")
router.register(r"alerts", views.AlertViewSet, basename="alerts")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", views.health, name="health"),
    path("api/auth/login/", views.login, name="login"),
    path("api/auth/me/", views.me, name="me"),
    path("api/readings/", views.readings, name="readings"),
    path("api/readings/batch/", views.batch_readings, name="batch-readings"),
    path("api/dashboard/", views.dashboard, name="dashboard"),
    path("api/worker/process-once/", views.process_once, name="process-once"),
    path("api/", include(router.urls)),
]
