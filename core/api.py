from rest_framework import permissions, viewsets

from .models import Client, ServiceRecord, Vehicle
from .policies import active_memberships_qs, user_organization_ids
from .serializers import ClientSerializer, ServiceRecordSerializer, VehicleSerializer


class PSBBaseViewSet(viewsets.ModelViewSet):
    """Ensure PSBs only see data for active memberships."""

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        org_ids = user_organization_ids(self.request.user)
        if not org_ids:
            return self.queryset.none()
        return self.queryset.filter(organization_id__in=org_ids)

    def perform_create(self, serializer):
        membership = (
            active_memberships_qs(self.request.user)
            .select_related("organization")
            .first()
        )
        if membership:
            serializer.save(organization=membership.organization)
        else:
            serializer.save()


class ClientViewSet(PSBBaseViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    filterset_fields = ["first_name", "last_name", "email"]


class VehicleViewSet(PSBBaseViewSet):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer
    filterset_fields = ["vin", "plate_number", "vehicle_type"]


class ServiceRecordViewSet(PSBBaseViewSet):
    queryset = ServiceRecord.objects.all()
    serializer_class = ServiceRecordSerializer
    filterset_fields = ["status", "service_type", "case_id"]

    def perform_create(self, serializer):
        membership = (
            active_memberships_qs(self.request.user)
            .select_related("organization")
            .first()
        )
        serializer.save(
            handled_by=self.request.user,
            organization=membership.organization if membership else None,
        )
