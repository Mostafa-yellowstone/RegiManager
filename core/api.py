from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import Client, ServiceRecord, Vehicle
from .policies import active_memberships_qs, user_organization_ids
from .serializers import ClientSerializer, ServiceRecordSerializer, VehicleSerializer


class PSBBaseViewSet(viewsets.ModelViewSet):
    """Ensure PSBs only see data for active memberships."""

    permission_classes = [permissions.IsAuthenticated]
    org_lookup = "organization_id"

    def get_queryset(self):
        org_ids = user_organization_ids(self.request.user)
        if not org_ids:
            return self.queryset.none()
        return self.queryset.filter(**{f"{self.org_lookup}__in": org_ids})

    def target_organization(self):
        """The PSB a new record belongs to: the requested one if the user is in it, else their first."""
        memberships = active_memberships_qs(self.request.user).select_related("organization")
        requested = (
            self.request.headers.get("X-Organization-Id")
            or self.request.data.get("organization_id")
            or self.request.query_params.get("organization_id")
        )
        if requested not in (None, ""):
            try:
                requested_id = int(requested)
            except (TypeError, ValueError):
                raise ValidationError({"organization_id": "Must be a number."})
            membership = memberships.filter(organization_id=requested_id).first()
            if membership is None:
                raise PermissionDenied("You are not a member of that PSB.")
            return membership.organization
        membership = memberships.order_by("organization__name").first()
        if membership is None:
            raise PermissionDenied("No active PSB membership.")
        return membership.organization

    def perform_create(self, serializer):
        serializer.save(organization=self.target_organization())


class ClientViewSet(PSBBaseViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    filterset_fields = ["first_name", "last_name", "email"]


class VehicleViewSet(PSBBaseViewSet):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer
    filterset_fields = ["client", "vin", "plate_number", "vehicle_type"]
    org_lookup = "client__organization_id"

    def perform_create(self, serializer):
        serializer.save()


class ServiceRecordViewSet(PSBBaseViewSet):
    queryset = ServiceRecord.objects.all()
    serializer_class = ServiceRecordSerializer
    filterset_fields = ["status", "service_type", "case_id"]

    def perform_create(self, serializer):
        serializer.save(
            handled_by=self.request.user,
            organization=self.target_organization(),
        )
