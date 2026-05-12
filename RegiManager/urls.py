"""
URL configuration for RegiManager project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include

from core.views import (
    dashboard,
    home,
    contact,
    privacy,
    login_view,
    logout_view,
    member_signup,
    update_agent_permissions,
    update_agent_role,
    all_agents_directory,
    agent_audit_view,
    monthly_report_pdf,
    daily_report_pdf,
    owner_report_pdf,
    service_receipt_pdf,
    mv82_form_pdf,
    generate_dmv_form,
    mv82_interactive,
    service_list,
    upload_document_ajax,
    get_documents,
    add_custom_service,
    all_service_types,
    audit_log_list,
    all_referrals,
    toggle_referral_partner,
    referral_profile,
    add_client,
    all_clients,
    client_detail,
    add_vehicle,
    vehicle_detail,
    edit_client,
    edit_service,
    edit_vehicle,
    start_process,
    upload_document_ajax_vehicle,
    get_documents_vehicle,
    check_vin_ajax,
    service_search_ajax,
    check_client_name_ajax,
    ocr_dl_ajax,
    ocr_vehicle_title_ajax,
    run_automation_scan,
    all_automation_logs,
    upcoming_expirations_view,
    bulk_send_reminders,
    finance_hub,
    save_finance_strategy_note,
    add_client_note,
    mark_client_note_done,
    open_notification,
    yearly_report_pdf,
    custom_range_report_pdf,
    send_manual_reminder,
    session_heartbeat,
    toggle_psb_automation,
    toggle_agent_active,
    switch_organization,
    get_client_details,
    branch_analytics,
    get_latest_news,
    public_intake_portal,
    public_intake_success,
    approve_intake,
    reject_intake,
)

from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from core.api import ClientViewSet, VehicleViewSet, ServiceRecordViewSet

router = DefaultRouter()
router.register(r'clients', ClientViewSet, basename='api-client')
router.register(r'vehicles', VehicleViewSet, basename='api-vehicle')
router.register(r'service-records', ServiceRecordViewSet, basename='api-service')

urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),
    path('admin/', admin.site.urls),
    
    # API Routes
    path('api/', include(router.urls)),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/docs/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    path("", home, name="home"),

    path("contact/", contact, name="contact"),
    path("privacy/", privacy, name="privacy"),
    path("auth/login/", login_view, name="login"),
    path("auth/logout/", logout_view, name="logout"),
    path("auth/member-signup/", member_signup, name="member-signup"),
    path("dashboard/", dashboard, name="dashboard"),
    path("dashboard/reports/owner-pdf/", owner_report_pdf, name="owner-report-pdf"),
    path("dashboard/reports/monthly-pdf/", monthly_report_pdf, name="monthly-report-pdf"),
    path("dashboard/reports/daily-pdf/", daily_report_pdf, name="daily-report-pdf"),
    path("dashboard/agent/permissions/", update_agent_permissions, name="update-agent-permissions"),
    path("dashboard/agent/role/", update_agent_role, name="update-agent-role"),
    path("dashboard/agents/", all_agents_directory, name="all-agents-directory"),
    path("dashboard/agents/<int:membership_id>/audit/", agent_audit_view, name="agent-audit"),
    path("dashboard/mv82-interactive/<int:service_id>/", mv82_interactive, name="mv82-interactive"),
    path("dashboard/receipts/<int:service_id>/", service_receipt_pdf, name="service-receipt-pdf"),
    path("dashboard/generate-form/<str:form_type>/<int:service_id>/", generate_dmv_form, name="generate-dmv-form"),
    path("dashboard/mv82-form/<int:service_id>/", mv82_form_pdf, name="mv82-form-pdf"),
    path("dashboard/services/all-types/", all_service_types, name="all-service-types"),
    path("dashboard/services/add-custom/", add_custom_service, name="add-custom-service"),
    path("dashboard/service/<str:service_type>/", service_list, name="service-list"),
    path("dashboard/audit-logs/", audit_log_list, name="all-audit-logs"),
    path("dashboard/service/<int:service_id>/upload/", upload_document_ajax, name="upload-document-ajax"),
    path("dashboard/service/<int:service_id>/docs/", get_documents, name="get-documents"),
    path("dashboard/referrals/", all_referrals, name="all-referrals"),
    path("dashboard/referrals/toggle-partner/", toggle_referral_partner, name="toggle-referral-partner"),
    path("dashboard/referrals/<int:referral_id>/", referral_profile, name="referral-profile"),
    path("dashboard/clients/", all_clients, name="all-clients"),
    path("dashboard/clients/add/", add_client, name="add-client"),
    path("dashboard/clients/<int:client_id>/", client_detail, name="client-detail"),
    path("dashboard/clients/<int:client_id>/add-vehicle/", add_vehicle, name="add-vehicle"),
    path("dashboard/vehicles/<int:vehicle_id>/", vehicle_detail, name="vehicle-detail"),
    path("dashboard/vehicles/<int:vehicle_id>/edit/", edit_vehicle, name="edit-vehicle"),
    path("dashboard/clients/<int:client_id>/edit/", edit_client, name="edit-client"),
    path("dashboard/vehicles/<int:vehicle_id>/start-process/", start_process, name="start-process"),
    path("dashboard/service/<int:service_id>/edit/", edit_service, name="edit-service"),
    path("dashboard/vehicle/<int:vehicle_id>/upload/", upload_document_ajax_vehicle, name="upload-document-ajax-vehicle"),
    path("dashboard/vehicle/<int:vehicle_id>/docs/", get_documents_vehicle, name="get-documents-vehicle"),
    path("dashboard/check-vin/", check_vin_ajax, name="check-vin"),
    path("dashboard/check-client-name/", check_client_name_ajax, name="check-client-name"),
    path("dashboard/service-search/", service_search_ajax, name="service-search-ajax"),
    path("dashboard/ocr-dl/", ocr_dl_ajax, name="ocr-dl"),
    path("dashboard/ocr-vehicle-title/", ocr_vehicle_title_ajax, name="ocr-vehicle-title"),
    path("dashboard/run-automation/", run_automation_scan, name="run-automation"),
    path("dashboard/vehicles/<int:vehicle_id>/send-reminder/", send_manual_reminder, name="send-manual-reminder"),
    path("dashboard/automation/logs/", all_automation_logs, name="all-automation-logs"),
    path("dashboard/automation/expirations/", upcoming_expirations_view, name="upcoming-expirations"),
    path("dashboard/automation/bulk-send/", bulk_send_reminders, name="bulk-send-reminders"),
    path("dashboard/finance/", finance_hub, name="finance-hub"),
    path("dashboard/finance/strategy-note/save/", save_finance_strategy_note, name="save-finance-strategy-note"),
    path("dashboard/clients/<int:client_id>/notes/add/", add_client_note, name="add-client-note"),
    path("dashboard/notes/<int:note_id>/done/", mark_client_note_done, name="mark-client-note-done"),
    path("dashboard/notifications/<int:notification_id>/open/", open_notification, name="open-notification"),
    path("dashboard/reports/yearly-pdf/", yearly_report_pdf, name="yearly-report-pdf"),
    path("dashboard/reports/custom-pdf/", custom_range_report_pdf, name="custom-pdf"),
    path("dashboard/psb/toggle-automation/", toggle_psb_automation, name="toggle-psb-automation"),
    path("dashboard/agent/toggle-active/", toggle_agent_active, name="toggle-agent-active"),
    path("dashboard/psb/switch/<int:org_id>/", switch_organization, name="switch-organization"),
    path("dashboard/get-client-details/<int:client_id>/", get_client_details, name="get-client-details"),
    path("dashboard/branch-analytics/<int:org_id>/", branch_analytics, name="branch-analytics"),
    path("api/get-latest-news/", get_latest_news, name="get-latest-news"),
    path("api/session-heartbeat/", session_heartbeat, name="session-heartbeat"),
    
    # Public Intake Routes
    path("intake/", public_intake_portal, name="public-intake-start"),
    path("intake/<str:portal_token>/", public_intake_portal, name="public-intake-direct"),
    path("intake/success/", public_intake_success, name="public-intake-success"),
    path("dashboard/intake/<int:intake_id>/approve/", approve_intake, name="approve-intake"),
    path("dashboard/intake/<int:intake_id>/reject/", reject_intake, name="reject-intake"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    
    # Catch-all to show the custom 404 page even in DEBUG mode for testing
    from django.urls import re_path
    from django.shortcuts import render
    urlpatterns += [
        re_path(r'^.*$', lambda request: render(request, '404.html', status=404))
    ]
