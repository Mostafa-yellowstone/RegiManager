from django.urls import path

from .api import ConnectionListView, ConnectivityDashboardView, RaterRequestView, SubmissionListView
from .views import (
    bind_quote,
    capture_client,
    capture_vehicle,
    certify_connection,
    client_vehicles,
    create_mock_market_bundle,
    inbound_webhook,
    rater_session,
    retry_dlq_item,
    select_rater_quote,
    start_rater,
    submit_to_market,
)

app_name = "regiconnect"

urlpatterns = [
    path("markets/mock-bundle/", create_mock_market_bundle, name="mock-bundle"),
    path("submissions/create/", submit_to_market, name="submit"),
    path("rater/start/", start_rater, name="rater-start"),
    path("rater/<int:request_id>/", rater_session, name="rater-session"),
    path("rater/quotes/<int:quote_id>/select/", select_rater_quote, name="rater-select"),
    path("capture/client/", capture_client, name="capture-client"),
    path("capture/vehicle/", capture_vehicle, name="capture-vehicle"),
    path("clients/vehicles/", client_vehicles, name="client-vehicles"),
    path("quotes/<int:quote_id>/bind/", bind_quote, name="bind"),
    path("dlq/<int:item_id>/retry/", retry_dlq_item, name="dlq-retry"),
    path("connections/<int:connection_id>/certify/", certify_connection, name="certify"),
]

api_urlpatterns = [
    path("webhooks/<int:connection_id>/", inbound_webhook, name="webhook"),
    path("dashboard/", ConnectivityDashboardView.as_view(), name="api-dashboard"),
    path("submissions/", SubmissionListView.as_view(), name="api-submissions"),
    path("connections/", ConnectionListView.as_view(), name="api-connections"),
    path("rater/requests/<int:request_id>/", RaterRequestView.as_view(), name="api-rater-request"),
]
