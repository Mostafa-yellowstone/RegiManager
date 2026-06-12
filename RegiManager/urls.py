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
    mark_site_news_read,
    public_intake_portal,
    public_intake_success,
    approve_intake,
    reject_intake,
    intake_mv82_pdf,
    portal_intake_list,
    outstanding_balances,
    mark_balance_paid,
    client_search_ajax,
    site_news_list,
    inventory_list,
    inventory_detail,
    delete_document,
    delete_service_record,
    generate_dmv_form_vehicle,
)


from rest_framework.routers import DefaultRouter
from core.views import (
    spaces_home,
    unlock_insurance_space,
    lock_insurance_space,
    toggle_insurance_lock,
    add_insurance_policy,
    edit_insurance_policy,
    view_insurance_policy_card,
    delete_insurance_policy,
    add_daily_payment,
    delete_daily_payment,
    toggle_daily_payment_clear,
    add_insurance_company,
    add_referral_category_option,
    add_insurance_type_option,
    delete_insurance_company,
    add_bank_account,
    edit_bank_account,
    delete_bank_account,
    add_bank_transaction,
    delete_bank_transaction,
    export_insurance_report_pdf,
    insurance_company_detail,
    insurance_company_ledger_fragment,
    toggle_policy_commission_received,
    insurance_company_upload_document,
    insurance_company_delete_document,
    insurance_agent_detail,
    add_knowledge_material,
    delete_knowledge_material,
)
from core.motorclub_views import (
    save_motorclub_config,
    add_motorclub_membership,
    add_motorclub_membership_from_client,
    edit_motorclub_membership,
    delete_motorclub_membership,
    add_motorclub_b2b_partner,
    delete_motorclub_b2b_partner,
)
from core.documents_views import (
    add_document_folder,
    edit_document_folder,
    add_document_type,
    edit_document_type,
    add_document_record,
    delete_document_record,
)
from core.inventory_views import (
    add_inventory_category,
    delete_inventory_category,
    add_inventory_product,
    edit_inventory_product,
    delete_inventory_product,
    adjust_inventory_stock,
    add_inventory_buyer,
    delete_inventory_buyer,
    add_inventory_invoice,
    delete_inventory_invoice,
    inventory_invoice_pdf,
    export_inventory_report,
    add_inventory_supplier,
    delete_inventory_supplier,
    add_inventory_purchase,
)
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
    path("dashboard/reports/monthly-pdf/", monthly_report_pdf, name="monthly-report-pdf"),
    path("dashboard/reports/daily-pdf/", daily_report_pdf, name="daily-report-pdf"),
    path("dashboard/agent/permissions/", update_agent_permissions, name="update-agent-permissions"),
    path("dashboard/agent/role/", update_agent_role, name="update-agent-role"),
    path("dashboard/agents/", all_agents_directory, name="all-agents-directory"),
    path("dashboard/agents/<int:membership_id>/audit/", agent_audit_view, name="agent-audit"),
    path("dashboard/mv82-interactive/<int:service_id>/", mv82_interactive, name="mv82-interactive"),
    path("dashboard/receipts/<int:service_id>/", service_receipt_pdf, name="service-receipt-pdf"),
    path("dashboard/generate-form/<str:form_type>/<int:service_id>/", generate_dmv_form, name="generate-dmv-form"),
    path("dashboard/generate-form-vehicle/<str:form_type>/<int:vehicle_id>/", generate_dmv_form_vehicle, name="generate-dmv-form-vehicle"),
    path("dashboard/mv82-form/<int:service_id>/", mv82_form_pdf, name="mv82-form-pdf"),
    path("dashboard/services/all-types/", all_service_types, name="all-service-types"),
    path("dashboard/services/add-custom/", add_custom_service, name="add-custom-service"),
    path("dashboard/service/<str:service_type>/", service_list, name="service-list"),
    path("dashboard/audit-logs/", audit_log_list, name="all-audit-logs"),
    path("dashboard/service/<int:service_id>/upload/", upload_document_ajax, name="upload-document-ajax"),
    path("dashboard/service/<int:service_id>/docs/", get_documents, name="get-documents"),
    path("dashboard/referrals/", all_referrals, name="all-referrals"),
    path("dashboard/referrals/category/add/", add_referral_category_option, name="add-referral-category"),
    path("dashboard/referrals/toggle-partner/", toggle_referral_partner, name="toggle-referral-partner"),
    path("dashboard/referrals/<int:referral_id>/", referral_profile, name="referral-profile"),
    path("dashboard/clients/", all_clients, name="all-clients"),
    path("dashboard/clients/add/", add_client, name="add-client"),
    path("dashboard/clients/<int:client_id>/", client_detail, name="client-detail"),
    path(
        "dashboard/clients/<int:client_id>/motorclub/add/",
        add_motorclub_membership_from_client,
        name="add-motorclub-membership-client",
    ),
    path("dashboard/clients/<int:client_id>/add-vehicle/", add_vehicle, name="add-vehicle"),
    path("dashboard/vehicles/<int:vehicle_id>/", vehicle_detail, name="vehicle-detail"),
    path("dashboard/vehicles/<int:vehicle_id>/edit/", edit_vehicle, name="edit-vehicle"),
    path("dashboard/clients/<int:client_id>/edit/", edit_client, name="edit-client"),
    path("dashboard/vehicles/<int:vehicle_id>/start-process/", start_process, name="start-process"),
    path("dashboard/service/<int:service_id>/edit/", edit_service, name="edit-service"),
    path("dashboard/vehicle/<int:vehicle_id>/upload/", upload_document_ajax_vehicle, name="upload-document-ajax-vehicle"),
    path("dashboard/vehicle/<int:vehicle_id>/docs/", get_documents_vehicle, name="get-documents-vehicle"),
    path("dashboard/docs/<int:doc_id>/delete/", delete_document, name="delete-document"),
    path("dashboard/service/<int:service_id>/delete/", delete_service_record, name="delete-service-record"),
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
    path("api/mark-site-news-read/", mark_site_news_read, name="mark-site-news-read"),
    path("api/session-heartbeat/", session_heartbeat, name="session-heartbeat"),
    
    # Public Intake Routes
    path("intake/", public_intake_portal, name="public-intake-start"),
    path("intake/success/", public_intake_success, name="public-intake-success"),
    path("intake/<str:portal_token>/", public_intake_portal, name="public-intake-direct"),
    path("dashboard/intake/portal-clients/", portal_intake_list, name="portal-intake-list"),
    path("dashboard/intake/<int:intake_id>/approve/", approve_intake, name="approve-intake"),
    path("dashboard/intake/<int:intake_id>/reject/", reject_intake, name="reject-intake"),
    path("intake/<int:intake_id>/mv82-preview/", intake_mv82_pdf, name="intake-mv82-pdf"),
    path("dashboard/outstanding-balances/", outstanding_balances, name="outstanding-balances"),
    path("dashboard/outstanding-balances/<int:record_id>/mark-paid/", mark_balance_paid, name="mark-balance-paid"),
    path("dashboard/client-search/", client_search_ajax, name="client-search-ajax"),
    
    # News & Inventory
    path("dashboard/site-news/", site_news_list, name="site-news-list"),
    path("dashboard/inventory/", inventory_list, name="inventory-list"),
    path("dashboard/inventory/<int:inventory_id>/", inventory_detail, name="inventory-detail"),
    
    # Spaces Hub and Insurance CRM / Banking Routes
    path("dashboard/spaces/", spaces_home, name="spaces-home"),
    path("dashboard/spaces/unlock/", unlock_insurance_space, name="unlock-insurance-space"),
    path("dashboard/spaces/lock/", lock_insurance_space, name="lock-insurance-space"),
    path("dashboard/spaces/toggle-password-protection/", toggle_insurance_lock, name="toggle-insurance-lock"),
    path("dashboard/spaces/insurance/policy/add/", add_insurance_policy, name="add-insurance-policy"),
    path("dashboard/spaces/insurance/policy/<int:policy_id>/edit/", edit_insurance_policy, name="edit-insurance-policy"),
    path("dashboard/spaces/insurance/policy/<int:policy_id>/card/", view_insurance_policy_card, name="view-insurance-policy-card"),
    path("dashboard/spaces/insurance/policy/<int:policy_id>/delete/", delete_insurance_policy, name="delete-insurance-policy"),
    path("dashboard/spaces/insurance/daily-payment/add/", add_daily_payment, name="add-daily-payment"),
    path("dashboard/spaces/insurance/daily-payment/<int:transaction_id>/delete/", delete_daily_payment, name="delete-daily-payment"),
    path("dashboard/spaces/insurance/daily-payment/<int:transaction_id>/clear/", toggle_daily_payment_clear, name="toggle-daily-payment-clear"),
    path("dashboard/spaces/insurance/company/add/", add_insurance_company, name="add-insurance-company"),
    path("dashboard/spaces/insurance/type/add/", add_insurance_type_option, name="add-insurance-type"),
    path("dashboard/spaces/insurance/company/<int:company_id>/delete/", delete_insurance_company, name="delete-insurance-company"),
    path("dashboard/spaces/banking/account/add/", add_bank_account, name="add-bank-account"),
    path("dashboard/spaces/banking/account/<int:account_id>/edit/", edit_bank_account, name="edit-bank-account"),
    path("dashboard/spaces/banking/account/<int:account_id>/delete/", delete_bank_account, name="delete-bank-account"),
    path("dashboard/spaces/banking/transaction/add/", add_bank_transaction, name="add-bank-transaction"),
    path("dashboard/spaces/banking/transaction/<int:transaction_id>/delete/", delete_bank_transaction, name="delete-bank-transaction"),
    path("dashboard/spaces/insurance/report/pdf/", export_insurance_report_pdf, name="export-insurance-report-pdf"),
    path("dashboard/spaces/insurance/company/<int:company_id>/", insurance_company_detail, name="insurance-company-detail"),
    path("dashboard/spaces/insurance/policy/<int:policy_id>/toggle-commission-received/", toggle_policy_commission_received, name="toggle-policy-commission-received"),
    path("dashboard/spaces/insurance/company/<int:company_id>/upload/", insurance_company_upload_document, name="insurance-company-upload-doc"),
    path("dashboard/spaces/insurance/company/doc/<int:doc_id>/delete/", insurance_company_delete_document, name="insurance-company-delete-doc"),
    path("dashboard/spaces/insurance/agent/<int:user_id>/", insurance_agent_detail, name="insurance-agent-detail"),
    path("dashboard/spaces/knowledge-hub/<int:space_id>/add/", add_knowledge_material, name="add-knowledge-material"),
    path("dashboard/spaces/knowledge-hub/material/<int:material_id>/delete/", delete_knowledge_material, name="delete-knowledge-material"),
    path("dashboard/spaces/inventory/<int:space_id>/category/add/", add_inventory_category, name="add-inventory-category"),
    path("dashboard/spaces/inventory/category/<int:category_id>/delete/", delete_inventory_category, name="delete-inventory-category"),
    path("dashboard/spaces/inventory/<int:space_id>/product/add/", add_inventory_product, name="add-inventory-product"),
    path("dashboard/spaces/inventory/product/<int:product_id>/edit/", edit_inventory_product, name="edit-inventory-product"),
    path("dashboard/spaces/inventory/product/<int:product_id>/delete/", delete_inventory_product, name="delete-inventory-product"),
    path("dashboard/spaces/inventory/product/<int:product_id>/adjust-stock/", adjust_inventory_stock, name="adjust-inventory-stock"),
    path("dashboard/spaces/inventory/<int:space_id>/buyer/add/", add_inventory_buyer, name="add-inventory-buyer"),
    path("dashboard/spaces/inventory/buyer/<int:buyer_id>/delete/", delete_inventory_buyer, name="delete-inventory-buyer"),
    path("dashboard/spaces/inventory/<int:space_id>/invoice/add/", add_inventory_invoice, name="add-inventory-invoice"),
    path("dashboard/spaces/inventory/invoice/<int:invoice_id>/delete/", delete_inventory_invoice, name="delete-inventory-invoice"),
    path("dashboard/spaces/inventory/invoice/<int:invoice_id>/pdf/", inventory_invoice_pdf, name="inventory-invoice-pdf"),
    path("dashboard/spaces/inventory/<int:space_id>/report/", export_inventory_report, name="export-inventory-report"),
    path("dashboard/spaces/inventory/<int:space_id>/supplier/add/", add_inventory_supplier, name="add-inventory-supplier"),
    path("dashboard/spaces/inventory/supplier/<int:supplier_id>/delete/", delete_inventory_supplier, name="delete-inventory-supplier"),
    path("dashboard/spaces/inventory/<int:space_id>/purchase/add/", add_inventory_purchase, name="add-inventory-purchase"),
    path("dashboard/spaces/motorclub/<int:space_id>/config/", save_motorclub_config, name="save-motorclub-config"),
    path("dashboard/spaces/motorclub/<int:space_id>/member/add/", add_motorclub_membership, name="add-motorclub-membership"),
    path("dashboard/spaces/motorclub/member/<int:membership_id>/edit/", edit_motorclub_membership, name="edit-motorclub-membership"),
    path("dashboard/spaces/motorclub/member/<int:membership_id>/delete/", delete_motorclub_membership, name="delete-motorclub-membership"),
    path("dashboard/spaces/motorclub/<int:space_id>/b2b/add/", add_motorclub_b2b_partner, name="add-motorclub-b2b-partner"),
    path("dashboard/spaces/motorclub/b2b/<int:partner_id>/delete/", delete_motorclub_b2b_partner, name="delete-motorclub-b2b-partner"),
    path("dashboard/spaces/documents/<int:space_id>/folder/add/", add_document_folder, name="add-document-folder"),
    path("dashboard/spaces/documents/folder/<int:folder_id>/edit/", edit_document_folder, name="edit-document-folder"),
    path("dashboard/spaces/documents/<int:space_id>/type/add/", add_document_type, name="add-document-type"),
    path("dashboard/spaces/documents/type/<int:type_id>/edit/", edit_document_type, name="edit-document-type"),
    path("dashboard/spaces/documents/<int:space_id>/record/add/", add_document_record, name="add-document-record"),
    path("dashboard/spaces/documents/record/<int:record_id>/delete/", delete_document_record, name="delete-document-record"),
]

from core.error_handlers import render_error_page

urlpatterns += [
    path("errors/502/", lambda request: render_error_page(request, 502)),
    path("errors/503/", lambda request: render_error_page(request, 503)),
    path(
        "dashboard/spaces/insurance/company/<int:company_id>/ledger/",
        insurance_company_ledger_fragment,
        name="insurance-company-ledger",
    ),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    from core.error_handlers import (
        custom_page_not_found,
        custom_permission_denied,
        render_error_page,
    )

    urlpatterns += [
        path("__preview__/404/", custom_page_not_found),
        path("__preview__/403/", custom_permission_denied),
        path("__preview__/500/", lambda request: render_error_page(request, 500)),
        path("__preview__/502/", lambda request: render_error_page(request, 502)),
        path("__preview__/503/", lambda request: render_error_page(request, 503)),
    ]


handler404 = "core.error_handlers.custom_page_not_found"
handler403 = "core.error_handlers.custom_permission_denied"
handler500 = "core.error_handlers.custom_server_error"
