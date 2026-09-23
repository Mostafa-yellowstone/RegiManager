"""Staff space CRM helpers."""

from django.db.models import Count, Q

from .models import StaffDocument, StaffEmployee


def staff_dashboard_stats(space):
    qs = StaffEmployee.objects.filter(space=space)
    by_status = {
        row["employment_status"]: row["count"]
        for row in qs.values("employment_status").annotate(count=Count("id"))
    }
    doc_count = StaffDocument.objects.filter(employee__space=space).count()
    return {
        "total_employees": qs.count(),
        "active_employees": by_status.get(StaffEmployee.StatusChoices.ACTIVE, 0),
        "on_leave": by_status.get(StaffEmployee.StatusChoices.ON_LEAVE, 0),
        "terminated": by_status.get(StaffEmployee.StatusChoices.TERMINATED, 0),
        "document_count": doc_count,
    }


def enrich_employee(employee):
    employee.status_label = employee.get_employment_status_display()
    employee.doc_count = getattr(employee, "annotated_doc_count", None)
    if employee.doc_count is None:
        employee.doc_count = employee.documents.count()
    return employee


def filter_employees(qs, *, search="", status=""):
    if search:
        qs = qs.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(email__icontains=search)
            | Q(phone__icontains=search)
            | Q(job_title__icontains=search)
            | Q(department__icontains=search)
        )
    if status:
        qs = qs.filter(employment_status=status)
    return qs
