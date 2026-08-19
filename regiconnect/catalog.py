"""Built-in connector rows."""

from .connectors.mock import MockCarrierConnector
from .connectors.skeleton import UnspecifiedCarrierConnector
from .models import Connector


def ensure_builtin_connectors():
    mock = MockCarrierConnector()
    Connector.objects.update_or_create(
        slug=mock.slug,
        defaults={
            "display_name": mock.display_name,
            "version": mock.version,
            "missing_carrier_spec": False,
            "capabilities": mock.capabilities(),
            "connector_type": "mock",
        },
    )
    spec = UnspecifiedCarrierConnector()
    Connector.objects.get_or_create(
        slug=spec.slug,
        defaults={
            "display_name": spec.display_name,
            "version": spec.version,
            "missing_carrier_spec": True,
            "capabilities": spec.capabilities(),
            "connector_type": "skeleton",
        },
    )
