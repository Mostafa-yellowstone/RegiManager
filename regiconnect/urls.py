from django.urls import path

from .api import ConnectionListView, ConnectivityDashboardView, SubmissionListView
from .views import (
    bind_quote,
    certify_connection,
    create_mock_market_bundle,
    inbound_webhook,
    retry_dlq_item,
    submit_to_market,
)

app_name = "regiconnect"

urlpatterns = [
    path("markets/mock-bundle/", create_mock_market_bundle, name="mock-bundle"),
    path("submissions/create/", submit_to_market, name="submit"),
    path("quotes/<int:quote_id>/bind/", bind_quote, name="bind"),
    path("dlq/<int:item_id>/retry/", retry_dlq_item, name="dlq-retry"),
    path("connections/<int:connection_id>/certify/", certify_connection, name="certify"),
]

api_urlpatterns = [
    path("webhooks/<int:connection_id>/", inbound_webhook, name="webhook"),
    path("dashboard/", ConnectivityDashboardView.as_view(), name="api-dashboard"),
    path("submissions/", SubmissionListView.as_view(), name="api-submissions"),
    path("connections/", ConnectionListView.as_view(), name="api-connections"),
]
