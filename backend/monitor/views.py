"""REST endpoints: API key for sensor writers; organizer token for management."""
import secrets
from django.conf import settings
from django.contrib.auth import authenticate
from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated, ValidationError
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from .models import Alert, Reading, Rule, Sensor
from .processor import audit_python, process_batch
from .serializers import AlertSerializer, ReadingOutSerializer, RuleSerializer, SensorSerializer
from .services import ingest


class IsOrganizer(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


def require_sensor_or_staff(request):
    provided = request.headers.get("X-Sensor-Key", "")
    configured = settings.SENSOR_API_KEY
    if (configured and len(configured) >= 16 and provided and secrets.compare_digest(provided, configured)):
        return
    if request.user.is_authenticated and request.user.is_staff:
        return
    raise AuthenticationFailed("Provide a valid X-Sensor-Key or an organizer token.")


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return Response({"status": "ok", "service": "CampusPulse API"})


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    credentials = request.data if isinstance(request.data, dict) else {}
    username = credentials.get("username", "")
    password = credentials.get("password", "")
    user = authenticate(request, username=username, password=password)
    if not user or not user.is_active or not user.is_staff:
        raise AuthenticationFailed("Invalid organizer credentials.")
    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key, "username": user.username, "is_staff": user.is_staff})


@api_view(["GET"])
@permission_classes([IsOrganizer])
def me(request):
    return Response({"username": request.user.username, "is_staff": True})


class SensorViewSet(viewsets.ModelViewSet):
    queryset = Sensor.objects.all()
    serializer_class = SensorSerializer
    permission_classes = [IsOrganizer]

    def get_queryset(self):
        return Sensor.objects.all().order_by("sensor_id")

    def destroy(self, request, *args, **kwargs):
        sensor = self.get_object()
        if sensor.readings.exists() or sensor.alerts.exists() or sensor.rules.exists():
            return Response({"detail": "Sensor has history or rules. Deactivate it instead."}, status=409)
        return super().destroy(request, *args, **kwargs)


class RuleViewSet(viewsets.ModelViewSet):
    queryset = Rule.objects.all().select_related("sensor")
    serializer_class = RuleSerializer
    permission_classes = [IsOrganizer]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        rule = self.get_object()
        if rule.alerts.exists():
            return Response({"detail": "Rule has past alerts. Disable it instead."}, status=409)
        return super().destroy(request, *args, **kwargs)


class AlertViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Alert.objects.select_related("sensor", "rule")
    serializer_class = AlertSerializer
    permission_classes = [IsOrganizer]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("status") in ("open", "acknowledged", "resolved"):
            qs = qs.filter(status=self.request.query_params["status"])
        if self.request.query_params.get("sensor"):
            qs = qs.filter(sensor__sensor_id=self.request.query_params["sensor"])
        return qs

    def _transition(self, pk, target, actor):
        with transaction.atomic():
            alert = Alert.objects.select_for_update().filter(pk=pk).first()
            if alert is None:
                from django.http import Http404
                raise Http404
            if alert.status == "resolved" or (target == "acknowledged" and alert.status != "open"):
                return Response({"detail": f"Cannot {target} an alert in status {alert.status}."}, status=409)
            old = alert.status
            alert.status = target
            now = timezone.now()
            if target == "acknowledged":
                alert.acknowledged_at = now
                alert.acknowledged_by = actor
                alert.save(update_fields=["status", "acknowledged_at", "acknowledged_by"])
            else:
                alert.resolved_at = now
                alert.resolved_by = actor
                alert.save(update_fields=["status", "resolved_at", "resolved_by"])
            audit_python(alert, old, actor=actor)
        return Response(AlertSerializer(alert).data)

    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        return self._transition(pk, "acknowledged", request.user)

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        return self._transition(pk, "resolved", request.user)


@api_view(["POST", "GET"])
@permission_classes([AllowAny])
def readings(request):
    if request.method == "POST":
        require_sensor_or_staff(request)
        result = ingest([request.data])
        return Response(result, status=status.HTTP_202_ACCEPTED)
    if not request.user.is_authenticated or not request.user.is_staff:
        raise NotAuthenticated("Organizer token required.")
    try:
        limit = max(1, min(int(request.query_params.get("limit", "100")), 1000))
    except ValueError:
        raise ValidationError({"limit": "Must be an integer."})
    query = Reading.objects.select_related("sensor").order_by("-recorded_at", "-id")
    if request.query_params.get("sensor"):
        query = query.filter(sensor__sensor_id=request.query_params["sensor"])
    if request.query_params.get("type"):
        query = query.filter(metric_type=request.query_params["type"])
    return Response(ReadingOutSerializer(query[:limit], many=True).data)


@api_view(["POST"])
@permission_classes([AllowAny])
def batch_readings(request):
    require_sensor_or_staff(request)
    payload = request.data.get("readings") if isinstance(request.data, dict) else request.data
    return Response(ingest(payload), status=status.HTTP_202_ACCEPTED)


@api_view(["GET"])
@permission_classes([IsOrganizer])
def dashboard(request):
    latest = list(Reading.objects.values("sensor__sensor_id", "metric_type")
                  .annotate(last_value_at=Max("recorded_at"))
                  .order_by("sensor__sensor_id", "metric_type")[:100])
    status_counts = dict(Alert.objects.values_list("status").annotate(total=Count("id")))
    return Response({
        "sensors": Sensor.objects.count(), "active_sensors": Sensor.objects.filter(is_active=True).count(),
        "enabled_rules": Rule.objects.filter(enabled=True).count(),
        "total_readings": Reading.objects.count(),
        "pending_readings": Reading.objects.filter(processed_at__isnull=True).count(),
        "alerts": {key: status_counts.get(key, 0) for key in ("open", "acknowledged", "resolved")},
        "sensor_metrics": latest,
        "recent_alerts": AlertSerializer(Alert.objects.select_related("sensor", "rule")[:10], many=True).data,
    })


@api_view(["POST"])
@permission_classes([IsOrganizer])
def process_once(request):
    try:
        limit = int(request.data.get("limit", 500))
    except (ValueError, TypeError):
        raise ValidationError({"limit": "Must be an integer."})
    return Response(process_batch(limit))
