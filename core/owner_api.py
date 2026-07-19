"""Owner companion API — finance, spaces, processes, and notifications."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .finance_hub_metrics import (
    build_daily_payment_cards,
    build_insurance_daily_payment_cards,
    build_month_goal_forecast,
)
from .models import (
    InsurancePolicy,
    Notification,
    Organization,
    OrganizationMembership,
    ServiceRecord,
)
from .owner_api_metrics import (
    build_dmv_finance_report,
    build_insurance_profit_report,
    build_location_comparison,
    build_month_comparison,
    build_process_summary,
    build_revenue_chart,
    build_space_period_profit,
    build_system_profit_summary,
    spaces_for_membership,
)
from .policies import active_memberships_qs, user_organization_ids


ORG_HEADER = "HTTP_X_ORGANIZATION_ID"


def _serialize_goal_forecast(data: dict) -> dict:
  out = dict(data)
  for key in (
      "mtd_revenue",
      "prev_month_revenue",
      "suggested_goal",
      "daily_run_rate",
      "projected_month_end",
      "required_daily_pace",
      "pace_pct",
      "mtd_pct",
      "gap_to_goal",
  ):
      if key in out and isinstance(out[key], Decimal):
          out[key] = str(out[key].quantize(Decimal("0.01")))
  return out


def _serialize_daily_cards(cards, grand_total):
  return {
      "cards": [
          {**card, "total": str(card["total"].quantize(Decimal("0.01")))}
          for card in cards
      ],
      "grand_total": str(grand_total.quantize(Decimal("0.01"))),
  }


class OwnerAPIBase(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def resolve_context(self, request, *, require_owner: bool = False):
        org_ids = user_organization_ids(request.user)
        if not org_ids:
            raise PermissionDenied("No active PSB membership.")

        header_org = request.META.get(ORG_HEADER) or request.query_params.get("organization_id")
        if header_org and str(header_org).isdigit():
            selected_id = int(header_org)
            if selected_id not in org_ids:
                raise PermissionDenied("You do not have access to this PSB.")
            organizations = Organization.objects.filter(id=selected_id, is_active=True)
        else:
            organizations = Organization.objects.filter(id__in=org_ids, is_active=True)

        organization = organizations.first()
        if not organization:
            raise PermissionDenied("Organization not found.")

        membership = (
            active_memberships_qs(request.user)
            .filter(organization=organization)
            .select_related("organization")
            .first()
        )
        if not membership:
            raise PermissionDenied("Access denied.")

        if require_owner and membership.role != OrganizationMembership.Role.OWNER:
            raise PermissionDenied("Owner access required.")

        records = ServiceRecord.objects.filter(organization=organization)
        today = timezone.localdate()
        return organization, membership, organizations, records, today

    def can_view_finance(self, membership: OrganizationMembership) -> bool:
        return (
            membership.role == OrganizationMembership.Role.OWNER
            or membership.can_view_reports
            or membership.can_view_net_profit
        )

    def can_view_spaces(self, membership: OrganizationMembership) -> bool:
        return membership.role == OrganizationMembership.Role.OWNER or membership.can_view_spaces


class OwnerOverviewView(OwnerAPIBase):
    """Combined owner dashboard: DMV + insurance + spaces profit and process counts."""

    def get(self, request):
        organization, membership, organizations, records, today = self.resolve_context(request)
        if not self.can_view_finance(membership):
            raise PermissionDenied("Finance access is disabled for your account.")

        payload = {
            "organization": {
                "id": organization.id,
                "name": organization.name,
                "city": organization.city,
                "state": organization.state,
            },
            "profit": build_system_profit_summary(organization, membership, records, today),
            "processes": build_process_summary(organization, today),
        }
        if membership.role == OrganizationMembership.Role.OWNER and organizations.count() > 1:
            payload["locations"] = build_location_comparison(organizations, today)
        return Response(payload)


class OwnerFinanceSummaryView(OwnerAPIBase):
    def get(self, request):
        organization, membership, _orgs, records, today = self.resolve_context(request)
        if not self.can_view_finance(membership):
            raise PermissionDenied("Finance access is disabled for your account.")

        org_ids = [organization.id]
        dmv_cards, dmv_total = build_daily_payment_cards(records, today)
        insurance_cards, insurance_total = build_insurance_daily_payment_cards(org_ids, today)
        forecast = build_month_goal_forecast(records, today)

        dmv_payload = build_dmv_finance_report(records, today)
        dmv_payload["daily_payments"] = _serialize_daily_cards(dmv_cards, dmv_total)

        insurance_payload = build_insurance_profit_report(organization.id, today)
        insurance_payload["daily_payments"] = _serialize_daily_cards(
            insurance_cards, insurance_total
        )

        return Response(
            {
                "dmv": dmv_payload,
                "insurance": insurance_payload,
                "goal_forecast": _serialize_goal_forecast(forecast),
            }
        )


class OwnerFinanceCompareView(OwnerAPIBase):
    def get(self, request):
        _org, membership, _orgs, records, _today = self.resolve_context(request)
        if not self.can_view_finance(membership):
            raise PermissionDenied("Finance access is disabled for your account.")

        compare_a = request.query_params.get("compare_a", "").strip()
        compare_b = request.query_params.get("compare_b", "").strip()
        mode = request.query_params.get("mode", "month").strip().lower()
        if mode not in {"month", "quarter"}:
            mode = "month"
        if not compare_a or not compare_b:
            return Response(
                {"detail": "compare_a and compare_b query params are required (YYYY-MM)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = build_month_comparison(records, compare_a, compare_b, mode=mode)
        if not data:
            return Response(
                {"detail": "Invalid compare_a or compare_b month format. Use YYYY-MM."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(data)


class OwnerFinanceChartView(OwnerAPIBase):
    def get(self, request):
        _org, membership, _orgs, records, today = self.resolve_context(request)
        if not self.can_view_finance(membership):
            raise PermissionDenied("Finance access is disabled for your account.")
        months = request.query_params.get("months", "12")
        try:
            month_count = max(1, min(int(months), 24))
        except (TypeError, ValueError):
            month_count = 12
        return Response(build_revenue_chart(records, today, months=month_count))


class OwnerSpacesListView(OwnerAPIBase):
    def get(self, request):
        organization, membership, _orgs, _records, today = self.resolve_context(request)
        if not self.can_view_spaces(membership):
            raise PermissionDenied("Spaces access is disabled for your account.")

        spaces = []
        for space in spaces_for_membership(membership, organization):
            spaces.append(
                {
                    "id": space.id,
                    "key": space.key,
                    "label": space.label,
                    "description": space.description,
                    "profit": build_space_period_profit(space, today),
                }
            )
        return Response({"spaces": spaces})


class OwnerSpaceDetailView(OwnerAPIBase):
    def get(self, request, space_id: int):
        organization, membership, _orgs, _records, today = self.resolve_context(request)
        if not self.can_view_spaces(membership):
            raise PermissionDenied("Spaces access is disabled for your account.")

        space = spaces_for_membership(membership, organization).filter(id=space_id).first()
        if not space:
            return Response({"detail": "Space not found."}, status=status.HTTP_404_NOT_FOUND)

        payload = {
            "id": space.id,
            "key": space.key,
            "label": space.label,
            "description": space.description,
            "profit": build_space_period_profit(space, today),
        }
        if space.key == "insurance":
            payload["pipeline"] = build_insurance_profit_report(organization.id, today)["pipeline"]
        if space.key == "tlc":
            from .tlc_profitability import tlc_dashboard_stats

            payload["tlc_summary"] = tlc_dashboard_stats(space, today=today)
        return Response(payload)


class OwnerInsurancePoliciesView(OwnerAPIBase):
    def get(self, request):
        organization, membership, _orgs, _records, today = self.resolve_context(request)
        if not self.can_view_finance(membership):
            raise PermissionDenied("Finance access is disabled for your account.")

        qs = InsurancePolicy.objects.filter(organization=organization).select_related(
            "client",
            "insurance_company",
            "added_by",
        )
        stage = request.query_params.get("stage", "").strip()
        if stage in {"quote", "bound", "endorsement"}:
            qs = qs.filter(stage=stage)

        limit = request.query_params.get("limit", "50")
        try:
            limit_n = max(1, min(int(limit), 200))
        except (TypeError, ValueError):
            limit_n = 50

        policies = []
        for policy in qs.order_by("-bound_date", "-created_at")[:limit_n]:
            policies.append(
                {
                    "id": policy.id,
                    "policy_number": policy.policy_number,
                    "stage": policy.stage,
                    "status": policy.status,
                    "client_name": policy.client.name if policy.client_id else "",
                    "insurance_company": policy.insurance_company.name if policy.insurance_company_id else "",
                    "premium": str(policy.premium),
                    "commission_amount": str(policy.commission_amount or "0.00"),
                    "broker_fee": str(policy.broker_fee or "0.00"),
                    "bound_date": policy.bound_date.isoformat() if policy.bound_date else None,
                    "added_by": (
                        policy.added_by.get_full_name() or policy.added_by.username
                        if policy.added_by_id
                        else None
                    ),
                }
            )
        return Response({"policies": policies, "as_of": today.isoformat()})


class OwnerProcessesView(OwnerAPIBase):
    def get(self, request):
        organization, membership, _orgs, records, today = self.resolve_context(request)
        if not self.can_view_finance(membership):
            raise PermissionDenied("Finance access is disabled for your account.")

        recent_services = (
            records.select_related("handled_by", "vehicle", "vehicle__client")
            .order_by("-created_at")[:10]
        )
        recent = []
        for record in recent_services:
            recent.append(
                {
                    "id": record.id,
                    "case_id": record.case_id,
                    "service_type": record.service_type,
                    "status": record.status,
                    "client_name": record.client_name,
                    "processing_fee": str(record.processing_fee or "0.00"),
                    "transaction_date": (
                        record.transaction_date.isoformat() if record.transaction_date else None
                    ),
                    "handled_by": (
                        record.handled_by.get_full_name() or record.handled_by.username
                        if record.handled_by_id
                        else None
                    ),
                }
            )

        return Response(
            {
                "summary": build_process_summary(organization, today),
                "recent_services": recent,
            }
        )


class OwnerNotificationsView(OwnerAPIBase):
    def get(self, request):
        organization, membership, _orgs, _records, _today = self.resolve_context(request)
        if membership.role != OrganizationMembership.Role.OWNER and not self.can_view_finance(membership):
            raise PermissionDenied("Owner or finance access required.")

        qs = Notification.objects.filter(user=request.user).select_related(
            "client",
            "organization",
            "policy",
            "insurance_company",
        )
        event_type = request.query_params.get("event_type", "").strip()
        if event_type:
            qs = qs.filter(event_type=event_type)
        if organization:
            qs = qs.filter(Q(organization=organization) | Q(organization__isnull=True))

        unread_only = request.query_params.get("unread", "").strip() in {"1", "true", "yes"}
        if unread_only:
            qs = qs.filter(is_read=False)

        limit = request.query_params.get("limit", "50")
        try:
            limit_n = max(1, min(int(limit), 200))
        except (TypeError, ValueError):
            limit_n = 50

        items = []
        for note in qs.order_by("-created_at")[:limit_n]:
            items.append(
                {
                    "id": note.id,
                    "event_type": note.event_type or "general",
                    "title": note.title,
                    "message": note.message,
                    "level": note.level,
                    "is_read": note.is_read,
                    "created_at": note.created_at.isoformat(),
                    "client_name": note.client.name if note.client_id else None,
                    "insurance_company_id": note.insurance_company_id,
                    "insurance_company_name": (
                        note.insurance_company.name if note.insurance_company_id else None
                    ),
                    "organization_id": note.organization_id,
                    "policy_id": note.policy_id,
                }
            )
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({"notifications": items, "unread_count": unread_count})


class OwnerNotificationReadView(OwnerAPIBase):
    def post(self, request, notification_id: int):
        note = Notification.objects.filter(user=request.user, id=notification_id).first()
        if not note:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        note.is_read = True
        note.save(update_fields=["is_read"])
        return Response({"detail": "Marked read."})


class OwnerNotificationMarkAllReadView(OwnerAPIBase):
    def post(self, request):
        updated = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({"detail": "Marked read.", "updated": updated})
