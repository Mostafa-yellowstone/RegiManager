from .mock import MockCarrierConnector
from .skeleton import UnspecifiedCarrierConnector

CONNECTORS = {
    MockCarrierConnector.slug: MockCarrierConnector,
    UnspecifiedCarrierConnector.slug: UnspecifiedCarrierConnector,
}


def get_connector(slug: str):
    cls = CONNECTORS.get(slug)
    if cls is None:
        return UnspecifiedCarrierConnector()
    return cls()
