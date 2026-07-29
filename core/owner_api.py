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
    build_insurance_payment_cards_for_range,
    build_month_goal_forecast,
    build_payment_cards_for_range,
)
from .models import (
    DailyPaymentTransaction,
    InsurancePolicy,
    MotorclubMembership,
    Notification,
    Organization,
    OrganizationMembership,
    ServiceRecord,
)
from .motorclub_crm import (
    build_motorclub_owner_summary,
    list_motorclub_memberships_for_org,
)
from .owner_space_companion import (
    build_documents_owner_summary,
    build_inventory_owner_summary,
    build_knowledge_owner_summary,
    build_tlc_owner_summary,
    list_document_records_for_org,
    list_inventory_products_for_org,
    list_knowledge_materials_for_org,
    list_tlc_policies_for_org,
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
from .owner_date_range import parse_owner_date_range
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
    serialized = []
    for card in cards:
        total = card.get("total", card.get("amount", Decimal("0")))
        if isinstance(total, Decimal):
            total_str = str(total.quantize(Decimal("0.01")))
        else:
            total_str = str(total)
        serialized.append(
            {
                **{k: v for k, v in card.items() if k not in {"total", "amount"}},
                "total": total_str,
                "amount": total_str,
                "count": int(card.get("count") or 0),
                "method": card.get("method") or card.get("key") or "",
                "key": card.get("key") or card.get("method") or "",
            }
        )
    return {
        "cards": serialized,
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

        custom_range = parse_owner_date_range(request.query_params)
        payload = {
            "organization": {
                "id": organization.id,
                "name": organization.name,
                "city": organization.city,
                "state": organization.state,
            },
            "profit": build_system_profit_summary(
                organization,
                membership,
                records,
                today,
                custom_range=custom_range,
            ),
            "processes": build_process_summary(organization, today),
        }
        if custom_range:
            start, end = custom_range
            payload["range"] = {
                "from": start.isoformat(),
                "to": end.isoformat(),
                "source": "ledger",
            }
        if membership.role == OrganizationMembership.Role.OWNER and organizations.count() > 1:
            payload["locations"] = build_location_comparison(organizations, today)
        return Response(payload)


class OwnerFinanceSummaryView(OwnerAPIBase):
    def get(self, request):
        organization, membership, _orgs, records, today = self.resolve_context(request)
        if not self.can_view_finance(membership):
            raise PermissionDenied("Finance access is disabled for your account.")

        custom_range = parse_owner_date_range(request.query_params)
        org_ids = [organization.id]
        if custom_range:
            start, end = custom_range
            dmv_cards, dmv_total = build_payment_cards_for_range(records, start, end)
            insurance_cards, insurance_total = build_insurance_payment_cards_for_range(
                org_ids, start, end
            )
        else:
            dmv_cards, dmv_total = build_daily_payment_cards(records, today)
            insurance_cards, insurance_total = build_insurance_daily_payment_cards(org_ids, today)
        forecast = build_month_goal_forecast(records, today)

        dmv_payload = build_dmv_finance_report(records, today, custom_range=custom_range)
        dmv_payload["daily_payments"] = _serialize_daily_cards(dmv_cards, dmv_total)

        insurance_payload = build_insurance_profit_report(
            organization.id, today, custom_range=custom_range
        )
        insurance_payload["daily_payments"] = _serialize_daily_cards(
            insurance_cards, insurance_total
        )

        payload = {
            "dmv": dmv_payload,
            "insurance": insurance_payload,
            "goal_forecast": _serialize_goal_forecast(forecast),
        }
        if custom_range:
            start, end = custom_range
            payload["range"] = {
                "from": start.isoformat(),
                "to": end.isoformat(),
                "source": "ledger",
            }
        return Response(payload)


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


class OwnerFinanceRecordsView(OwnerAPIBase):
    """Ledger payment rows for Finance method drill-down."""

    def get(self, request):
        organization, membership, _orgs, records, today = self.resolve_context(request)
        if not self.can_view_finance(membership):
            raise PermissionDenied("Finance access is disabled for your account.")

        category = (request.query_params.get("category") or "dmv").strip().lower()
        if category not in {"dmv", "insurance"}:
            return Response(
                {"detail": "category must be dmv or insurance."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        method = (request.query_params.get("method") or "").strip().lower()
        method_aliases = {
            "card": "credit_card",
            "credit": "credit_card",
            "credit_card": "credit_card",
            "cash": "cash",
            "zelle": "zelle",
            "checks": "checks",
            "check": "checks",
        }
        method_key = method_aliases.get(method, method) if method else ""

        custom_range = parse_owner_date_range(request.query_params)
        if custom_range:
            start, end = custom_range
        else:
            timeframe = (request.query_params.get("timeframe") or "daily").strip().lower()
            if timeframe == "monthly":
                start, end = today.replace(day=1), today
            else:
                start, end = today, today

        limit = request.query_params.get("limit", "100")
        try:
            limit_n = max(1, min(int(limit), 500))
        except (TypeError, ValueError):
            limit_n = 100

        results = []
        if category == "dmv":
            qs = records.filter(
                transaction_date__gte=start,
                transaction_date__lte=end,
            ).exclude(status="refund").order_by("-transaction_date", "-id")
            for record in qs[: limit_n * 2]:
                for method_name, amount in (
                    (record.payment_method, record.paid_amount or record.service_fee),
                    (record.payment_method_2, record.paid_amount_2),
                ):
                    if not method_name or amount is None:
                        continue
                    bucket = method_name
                    if method_name in {"visa", "mastercard", "discover", "diners_club", "american_express"}:
                        bucket = "credit_card"
                    if method_key and bucket != method_key and method_name != method_key:
                        continue
                    results.append(
                        {
                            "id": f"dmv_{record.id}_{method_name}",
                            "transaction_date": (
                                record.transaction_date.isoformat()
                                if record.transaction_date
                                else ""
                            ),
                            "description": record.service_type or "DMV service",
                            "method": "card" if bucket == "credit_card" else bucket,
                            "amount": str(Decimal(amount or 0).quantize(Decimal("0.01"))),
                            "client_name": record.client_name or "",
                            "reference": record.receipt_number or record.case_id or "",
                        }
                    )
                    if len(results) >= limit_n:
                        break
                if len(results) >= limit_n:
                    break
        else:
            qs = DailyPaymentTransaction.objects.filter(
                organization=organization,
                transaction_date__gte=start,
                transaction_date__lte=end,
            ).select_related("client", "recorded_by").order_by("-transaction_date", "-id")
            if method_key:
                qs = qs.filter(payment_method=method_key)

            # Advanced filters for Insurance Space daily payments ledger.
            payment_type = (request.query_params.get("payment_type") or "").strip().lower()
            search_q = (request.query_params.get("q") or "").strip()
            min_amount = (request.query_params.get("min_amount") or "").strip()
            max_amount = (request.query_params.get("max_amount") or "").strip()
            if payment_type:
                qs = qs.filter(payment_type=payment_type)
            if search_q:
                from django.db.models import Q

                qs = qs.filter(
                    Q(client__name__icontains=search_q)
                    | Q(notes__icontains=search_q)
                    | Q(recorded_by__username__icontains=search_q)
                    | Q(recorded_by__first_name__icontains=search_q)
                    | Q(recorded_by__last_name__icontains=search_q)
                )
            if min_amount:
                try:
                    qs = qs.filter(amount__gte=Decimal(min_amount))
                except Exception:
                    pass
            if max_amount:
                try:
                    qs = qs.filter(amount__lte=Decimal(max_amount))
                except Exception:
                    pass

            for tx in qs[:limit_n]:
                agent = ""
                if tx.recorded_by_id:
                    agent = (
                        tx.recorded_by.get_full_name().strip()
                        or tx.recorded_by.username
                        or ""
                    )
                results.append(
                    {
                        "id": f"ins_{tx.id}",
                        "transaction_date": tx.transaction_date.isoformat(),
                        "description": tx.get_payment_type_display(),
                        "payment_type": tx.payment_type,
                        "method": "card" if tx.payment_method == "credit_card" else tx.payment_method,
                        "amount": str(Decimal(tx.amount or 0).quantize(Decimal("0.01"))),
                        "client_name": str(tx.client) if tx.client_id else "",
                        "reference": str(tx.insurance_policy_id or tx.id),
                        "notes": tx.notes or "",
                        "agent_name": agent,
                    }
                )

        return Response(
            {
                "results": results,
                "count": len(results),
                "range": {
                    "from": start.isoformat(),
                    "to": end.isoformat(),
                    "source": "ledger",
                },
            }
        )


def _flatten_space_payload(space, profit: dict) -> dict:
    """Expose period buckets at top-level for companion clients."""
    return {
        "id": str(space.id),
        "key": space.key,
        "name": space.label,
        "label": space.label,
        "description": space.description,
        "today": profit.get("today", {"profit": "0.00", "revenue": "0.00"}),
        "month": profit.get("month", {"profit": "0.00", "revenue": "0.00"}),
        "year": profit.get("year", {"profit": "0.00", "revenue": "0.00"}),
        "custom": profit.get("custom", {"profit": "0.00", "revenue": "0.00"}),
        "profit": profit,
        "active_memberships": profit.get("active_memberships"),
        "inventory_value": profit.get("inventory_value"),
        "total_records": profit.get("total_records"),
        "range": profit.get("range"),
    }


class OwnerSpacesListView(OwnerAPIBase):
    def get(self, request):
        organization, membership, _orgs, _records, today = self.resolve_context(request)
        if not self.can_view_spaces(membership):
            raise PermissionDenied("Spaces access is disabled for your account.")

        custom_range = parse_owner_date_range(request.query_params)
        spaces = []
        for space in spaces_for_membership(membership, organization):
            profit = build_space_period_profit(space, today, custom_range=custom_range)
            spaces.append(_flatten_space_payload(space, profit))
        payload = {"spaces": spaces, "results": spaces}
        if custom_range:
            start, end = custom_range
            payload["range"] = {
                "from": start.isoformat(),
                "to": end.isoformat(),
                "source": "ledger",
            }
        return Response(payload)


class OwnerSpaceDetailView(OwnerAPIBase):
    def get(self, request, space_id: int):
        organization, membership, _orgs, _records, today = self.resolve_context(request)
        if not self.can_view_spaces(membership):
            raise PermissionDenied("Spaces access is disabled for your account.")

        space = spaces_for_membership(membership, organization).filter(id=space_id).first()
        if not space:
            return Response({"detail": "Space not found."}, status=status.HTTP_404_NOT_FOUND)

        custom_range = parse_owner_date_range(request.query_params)
        profit = build_space_period_profit(space, today, custom_range=custom_range)
        payload = _flatten_space_payload(space, profit)
        if space.key == "insurance":
            payload["pipeline"] = build_insurance_profit_report(
                organization.id, today, custom_range=custom_range
            )["pipeline"]
        if space.key == "tlc":
            payload["tlc_summary"] = build_tlc_owner_summary(space, today=today)
            payload["tlc_policies"] = list_tlc_policies_for_org(
                organization, status="active", limit=50
            )
        if space.key == "motorclub":
            summary = build_motorclub_owner_summary(space)
            payload["motorclub_summary"] = summary
            payload["motorclub_memberships"] = list_motorclub_memberships_for_org(
                organization,
                status="active",
                limit=50,
            )
        if space.key == "custom_inventory":
            payload["inventory_summary"] = build_inventory_owner_summary(space)
            payload["inventory_items"] = list_inventory_products_for_org(
                organization, stock_status=None, limit=50
            )
        if space.key == "documents":
            payload["documents_summary"] = build_documents_owner_summary(space)
            payload["vault_documents"] = list_document_records_for_org(
                organization, limit=50
            )
        if space.key == "knowledge_hub":
            payload["knowledge_summary"] = build_knowledge_owner_summary(space)
            payload["knowledge_articles"] = list_knowledge_materials_for_org(
                organization, limit=50
            )
        return Response(payload)


class OwnerMotorclubMembershipsView(OwnerAPIBase):
    """List Motor Club memberships for the companion Motorclub space."""

    VALID_STATUSES = {
        MotorclubMembership.StatusChoices.ACTIVE,
        MotorclubMembership.StatusChoices.PENDING,
        MotorclubMembership.StatusChoices.CANCELLED,
        MotorclubMembership.StatusChoices.EXPIRED,
    }
    VALID_CHANNELS = {
        MotorclubMembership.ChannelChoices.INSURANCE_CLIENT,
        MotorclubMembership.ChannelChoices.B2B,
        MotorclubMembership.ChannelChoices.DIRECT,
    }

    def get(self, request):
        organization, membership, _orgs, _records, today = self.resolve_context(request)
        if not self.can_view_spaces(membership):
            raise PermissionDenied("Spaces access is disabled for your account.")

        status_filter = request.query_params.get("status", "").strip().lower()
        if status_filter and status_filter not in self.VALID_STATUSES:
            return Response(
                {"detail": "status must be active, pending, cancelled, or expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        channel = request.query_params.get("channel", "").strip().lower()
        if channel and channel not in self.VALID_CHANNELS:
            return Response(
                {
                    "detail": "channel must be insurance_client, b2b, or direct.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        limit = request.query_params.get("limit", "50")
        try:
            limit_n = max(1, min(int(limit), 200))
        except (TypeError, ValueError):
            limit_n = 50

        memberships = list_motorclub_memberships_for_org(
            organization,
            status=status_filter or None,
            channel=channel or None,
            limit=limit_n,
        )
        return Response(
            {
                "memberships": memberships,
                "results": memberships,
                "as_of": today.isoformat(),
            }
        )


def _parse_limit(request, default: int = 50) -> int:
    limit = request.query_params.get("limit", str(default))
    try:
        return max(1, min(int(limit), 200))
    except (TypeError, ValueError):
        return default


class OwnerTlcPoliciesView(OwnerAPIBase):
    def get(self, request):
        from .tlc_models import TLCPolicy as TLCPolicyModel

        organization, membership, _orgs, _records, today = self.resolve_context(request)
        if not self.can_view_spaces(membership):
            raise PermissionDenied("Spaces access is disabled for your account.")

        status_filter = request.query_params.get("status", "").strip().lower()
        allowed = {
            TLCPolicyModel.Status.ACTIVE,
            TLCPolicyModel.Status.PENDING,
            TLCPolicyModel.Status.CANCELLED,
            TLCPolicyModel.Status.SUSPENDED,
            TLCPolicyModel.Status.EXPIRED,
            TLCPolicyModel.Status.REINSTATED,
        }
        if status_filter and status_filter not in allowed:
            return Response(
                {
                    "detail": "status must be active, pending, cancelled, suspended, expired, or reinstated.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        policies = list_tlc_policies_for_org(
            organization,
            status=status_filter or None,
            limit=_parse_limit(request),
        )
        return Response({"policies": policies, "results": policies, "as_of": today.isoformat()})


class OwnerInventoryProductsView(OwnerAPIBase):
    VALID_STOCK = {"normal", "low_stock", "out_of_stock"}

    def get(self, request):
        organization, membership, _orgs, _records, today = self.resolve_context(request)
        if not self.can_view_spaces(membership):
            raise PermissionDenied("Spaces access is disabled for your account.")

        stock = request.query_params.get("stock_status", "").strip().lower()
        if stock and stock not in self.VALID_STOCK:
            return Response(
                {"detail": "stock_status must be normal, low_stock, or out_of_stock."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        items = list_inventory_products_for_org(
            organization,
            stock_status=stock or None,
            limit=_parse_limit(request),
        )
        return Response({"items": items, "results": items, "as_of": today.isoformat()})


class OwnerDocumentRecordsView(OwnerAPIBase):
    def get(self, request):
        organization, membership, _orgs, _records, today = self.resolve_context(request)
        if not self.can_view_spaces(membership):
            raise PermissionDenied("Spaces access is disabled for your account.")

        doc_type = request.query_params.get("doc_type", "").strip()
        records = list_document_records_for_org(
            organization,
            doc_type=doc_type or None,
            limit=_parse_limit(request),
        )
        return Response({"documents": records, "results": records, "as_of": today.isoformat()})


class OwnerKnowledgeMaterialsView(OwnerAPIBase):
    def get(self, request):
        organization, membership, _orgs, _records, today = self.resolve_context(request)
        if not self.can_view_spaces(membership):
            raise PermissionDenied("Spaces access is disabled for your account.")

        roadmap = request.query_params.get("roadmap", "").strip()
        materials = list_knowledge_materials_for_org(
            organization,
            roadmap=roadmap or None,
            limit=_parse_limit(request),
        )
        return Response({"articles": materials, "results": materials, "as_of": today.isoformat()})


class OwnerInsurancePoliciesView(OwnerAPIBase):
    def get(self, request):
        organization, membership, _orgs, _records, today = self.resolve_context(request)
        if not self.can_view_finance(membership):
            raise PermissionDenied("Finance access is disabled for your account.")

        from .insurance_space_metrics import filter_policies_by_quote_period
        from .owner_date_range import parse_owner_date_range

        qs = InsurancePolicy.objects.filter(organization=organization).select_related(
            "client",
            "insurance_company",
            "added_by",
        )
        stage = request.query_params.get("stage", "").strip()
        if stage in {"quote", "bound", "endorsement"}:
            qs = qs.filter(stage=stage)

        custom_range = parse_owner_date_range(request.query_params)
        if custom_range:
            start, end = custom_range
            qs = filter_policies_by_quote_period(qs, start, end)

        limit = request.query_params.get("limit", "200")
        try:
            limit_n = max(1, min(int(limit), 500))
        except (TypeError, ValueError):
            limit_n = 200

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
        return Response(
            {
                "policies": policies,
                "count": len(policies),
                "as_of": today.isoformat(),
            }
        )


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
                    "timestamp": note.created_at.isoformat(),
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
