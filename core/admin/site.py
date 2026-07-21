from django.contrib import admin
from django.urls import path

from ..admin_views import crm_import_view, psb_backup_download, psb_backup_import
from .grouping import group_core_models, split_core_app_entry


def patch_admin_site(site=None):
    site = site or admin.site
    original_get_app_list = site.get_app_list

    def grouped_get_app_list(request, app_label=None):
        app_list = original_get_app_list(request, app_label)
        if app_label is not None and app_label != "core":
            return app_list

        result = []
        for app_entry in app_list:
            if app_entry["app_label"] != "core":
                result.append(app_entry)
                continue
            result.extend(split_core_app_entry(app_entry))
        return result

    site.get_app_list = grouped_get_app_list

    original_get_urls = site.get_urls

    def custom_get_urls():
        urls = original_get_urls()
        custom_urls = [
            path("crm-import/", site.admin_view(crm_import_view), name="crm-import"),
            path(
                "psb-backup/import/",
                site.admin_view(psb_backup_import),
                name="psb-backup-import",
            ),
            path(
                "psb-backup/download/<int:org_id>/",
                site.admin_view(psb_backup_download),
                name="psb-backup-download",
            ),
        ]
        return custom_urls + urls

    site.get_urls = custom_get_urls

    original_app_index = site.app_index

    def grouped_app_index(request, app_label, extra_context=None):
        extra_context = extra_context or {}
        if app_label == "core":
            app_dict = site._build_app_dict(request, app_label)
            extra_context["core_admin_groups"] = group_core_models(app_dict.get("models", []))
        return original_app_index(request, app_label, extra_context=extra_context)

    site.app_index = grouped_app_index

    site.site_header = "RegiManager Administration"
    site.site_title = "RegiManager Admin"
    site.index_title = "Operations Dashboard"
