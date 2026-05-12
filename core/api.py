from rest_framework import viewsets, permissions
from .models import Client, Vehicle, ServiceRecord, OrganizationMembership
from .serializers import ClientSerializer, VehicleSerializer, ServiceRecordSerializer

class PSBBaseViewSet(viewsets.ModelViewSet):
    """
    Base ViewSet to ensure psbs only see THEIR data.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Filter by the user's organizations
        user_orgs = OrganizationMembership.objects.filter(user=self.request.user).values_list('organization_id', flat=True)
        return self.queryset.filter(organization_id__in=user_orgs)

    def perform_create(self, serializer):
        # Automatically assign the first organization the user belongs to
        # (Enterprise improvement: allow specifying org if user in multiple)
        user_membership = OrganizationMembership.objects.filter(user=self.request.user).first()
        if user_membership:
            serializer.save(organization=user_membership.organization)
        else:
            serializer.save()

class ClientViewSet(PSBBaseViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    filterset_fields = ['first_name', 'last_name', 'email']

class VehicleViewSet(PSBBaseViewSet):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer
    filterset_fields = ['vin', 'plate_number', 'vehicle_type']

class ServiceRecordViewSet(PSBBaseViewSet):
    queryset = ServiceRecord.objects.all()
    serializer_class = ServiceRecordSerializer
    filterset_fields = ['status', 'service_type', 'case_id']

    def perform_create(self, serializer):
        user_membership = OrganizationMembership.objects.filter(user=self.request.user).first()
        serializer.save(
            handled_by=self.request.user,
            organization=user_membership.organization if user_membership else None
        )
