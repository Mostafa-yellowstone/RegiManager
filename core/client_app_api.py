"""Client mobile wallet API — end-customer access (not staff companion)."""

from __future__ import annotations

import time
from decimal import Decimal

from django.db.models import Q
from django.http import FileResponse, Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .client_app_auth import (
    ClientAppAuthentication,
    ClientAppLoginThrottle,
    IsClientAppAuthenticated,
    find_client_for_login,
    issue_session,
    resolve_organization,
    revoke_session,
)
from .client_app_serializers import (
    build_alerts,
    build_client_receipts,
    build_client_vehicles,
    build_upcoming_items,
    client_profile_payload,
    dmv_document_payload,
    insurance_document_payload,
    payment_payload,
    policy_detail_payload,
    policy_list_item,
    schedule_payload,
)
from .client_chat import (
    list_chat_messages,
    mark_read_by_client,
    post_client_message,
    serialize_chat_message,
    unread_for_client,
)
from .insurance_policy_schedule import summarize_insurance_schedule
from .models import (
    ClientChatMessage,
    DailyPaymentTransaction,
    InsurancePolicy,
    InsurancePolicyDocument,
    ServiceDocument,
    Vehicle,
)
from .realtime import wait_client_wake



class ClientAppAPIView(APIView):
    authentication_classes = [ClientAppAuthentication]
    permission_classes = [IsClientAppAuthenticated]


def _client_policies(client):
    return (
        InsurancePolicy.objects.filter(client=client)
        .select_related("insurance_company")
        .order_by("-created_at")
    )


def _client_dmv_documents(client, *, identity_cards_only=False):
    qs = ServiceDocument.objects.filter(
        Q(vehicle__client=client) | Q(service_record__vehicle__client=client),
    ).select_related("vehicle", "service_record")
    if identity_cards_only:
        qs = qs.filter(document_type__in=("insurance_id", "driver_license"))
    return qs.distinct().order_by("-uploaded_at")


def _client_insurance_documents(client, *, document_types=None):
    qs = InsurancePolicyDocument.objects.filter(policy__client=client).select_related("policy")
    if document_types:
        qs = qs.filter(document_type__in=document_types)
    return qs.order_by("-uploaded_at")


def _client_payments(client):
    return (
        DailyPaymentTransaction.objects.filter(client=client)
        .select_related("insurance_company", "insurance_policy")
        .order_by("-transaction_date", "-id")
    )


def _client_vehicles(client):
    return Vehicle.objects.filter(client=client).order_by("-id")


def _best_next_payment(client) -> dict | None:
    best = None
    for policy in _client_policies(client):
        summary = summarize_insurance_schedule(policy)
        due_date = summary.get("next_due_date")
        if not due_date:
            continue
        remaining_amount = sum(
            (r.total_due for r in summary["installments"] if not r.is_paid),
            Decimal("0.00"),
        )
        paid_amount = sum(
            (r.total_due for r in summary["installments"] if r.is_paid),
            Decimal("0.00"),
        )
        candidate = {
            "due_date": due_date.isoformat(),
            "amount": f"{summary['next_due_amount']:.2f}" if summary.get("next_due_amount") is not None else None,
            "policy_id": policy.id,
            "policy_number": policy.policy_number,
            "company": policy.insurance_company.name if policy.insurance_company_id else "",
            "paid_amount": f"{paid_amount:.2f}",
            "remaining_amount": f"{remaining_amount:.2f}",
            "paid_count": summary["paid"],
            "remaining_payments": summary["open"],
            "total_installments": summary["total"],
        }
        if best is None or due_date < best["_sort"]:
            candidate["_sort"] = due_date
            best = candidate
    if best:
        best.pop("_sort", None)
    return best


class ClientLoginView(APIView):
    """
    Exchange org code + phone/email + PIN for a client session token.

    Header on subsequent requests: Authorization: Token <token>
    """

    authentication_classes = []
    permission_classes = []
    throttle_classes = [ClientAppLoginThrottle]

    def post(self, request):
        data = request.data if hasattr(request, "data") else {}
        portal_token = (data.get("portal_token") or "").strip()
        organization_id = data.get("organization_id")
        phone = (data.get("phone") or data.get("phone_number") or "").strip()
        email = (data.get("email") or "").strip()
        pin_raw = data.get("pin")
        pin = "".join(ch for ch in str(pin_raw if pin_raw is not None else "") if ch.isdigit())
        device_label = (data.get("device_label") or "")[:120]

        org = resolve_organization(portal_token=portal_token, organization_id=organization_id)
        if not org:
            return Response(
                {"detail": "Invalid organization or portal code."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not pin:
            return Response({"detail": "PIN is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not phone and not email:
            return Response(
                {"detail": "Phone or email is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        client = find_client_for_login(org, phone=phone, email=email, require_enabled=False)
        if not client:
            return Response(
                {
                    "detail": (
                        "No client found with that phone/email for this agency. "
                        "Use the exact phone or email on the client profile."
                    )
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not client.app_access_enabled:
            return Response(
                {
                    "detail": (
                        "Mobile app access is not enabled for this client. "
                        "Ask the agency to enable Client App Access and set a PIN."
                    )
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not client.app_pin_hash:
            return Response(
                {
                    "detail": "No PIN is set for this client. Ask the agency to set a PIN."
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not client.check_app_pin(pin):
            return Response(
                {"detail": "Incorrect PIN."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        session = issue_session(client, device_label=device_label)
        return Response(
            {
                "token": session.token,
                "client": client_profile_payload(client),
                "organization": {
                    "id": org.id,
                    "name": org.name,
                    "portal_token": org.portal_token or "",
                },
            }
        )


class ClientLogoutView(ClientAppAPIView):
    def post(self, request):
        revoke_session(getattr(request, "client_session", None))
        return Response({"detail": "Logged out."})


class ClientMeView(ClientAppAPIView):
    def get(self, request):
        return Response(client_profile_payload(request.client))


class ClientHomeView(ClientAppAPIView):
    def get(self, request):
        client = request.client
        policies = list(_client_policies(client)[:20])
        upcoming = build_upcoming_items(client, days=90)[:8]
        alerts = build_alerts(client)
        vehicles = build_client_vehicles(client)[:8]
        payments = list(_client_payments(client)[:8])
        receipts = build_client_receipts(client, limit=8)

        return Response(
            {
                "client": client_profile_payload(client),
                "organization_name": getattr(getattr(client, "organization", None), "name", "") or "",
                "next_payment": _best_next_payment(client),
                "upcoming": upcoming,
                "alerts": alerts,
                "alert_count": len(alerts),
                "chat_unread": unread_for_client(client),
                "vehicles": vehicles,
                "recent_payments": [payment_payload(p) for p in payments],
                "recent_receipts": receipts,
                "policies": [policy_list_item(p) for p in policies],
            }
        )


class ClientPoliciesView(ClientAppAPIView):
    def get(self, request):
        policies = list(_client_policies(request.client))
        return Response({"count": len(policies), "results": [policy_list_item(p) for p in policies]})


class ClientPolicyDetailView(ClientAppAPIView):
    def get(self, request, policy_id: int):
        policy = _client_policies(request.client).filter(id=policy_id).first()
        if not policy:
            raise Http404("Policy not found.")
        payload = policy_detail_payload(policy)
        payments = list(
            _client_payments(request.client).filter(
                Q(insurance_policy=policy) | Q(policy_number__iexact=policy.policy_number)
            )[:25]
        )
        payload["payments"] = [payment_payload(p) for p in payments]
        id_cards = list(
            _client_insurance_documents(
                request.client,
                document_types=[InsurancePolicyDocument.DocumentType.ID_CARDS],
            ).filter(policy=policy)
        )
        payload["id_cards"] = [insurance_document_payload(d, request=request) for d in id_cards]
        return Response(payload)


class ClientPolicyScheduleView(ClientAppAPIView):
    def get(self, request, policy_id: int):
        policy = _client_policies(request.client).filter(id=policy_id).first()
        if not policy:
            raise Http404("Policy not found.")
        return Response(schedule_payload(policy))


class ClientIdCardsView(ClientAppAPIView):
    """Insurance ID cards + driver licenses for the stylish identity pager."""

    def get(self, request):
        insurance_docs = list(
            _client_insurance_documents(
                request.client,
                document_types=[InsurancePolicyDocument.DocumentType.ID_CARDS],
            )
        )
        dmv_ids = list(_client_dmv_documents(request.client, identity_cards_only=True))
        results = [insurance_document_payload(d, request=request) for d in insurance_docs]
        results.extend(dmv_document_payload(d, request=request) for d in dmv_ids)
        results.sort(key=lambda row: row.get("uploaded_at") or "", reverse=True)
        return Response({"count": len(results), "results": results})


class ClientDocumentsView(ClientAppAPIView):
    """Full document vault — all insurance + DMV uploads for the client."""

    def get(self, request):
        insurance_docs = list(_client_insurance_documents(request.client))
        dmv_docs = list(_client_dmv_documents(request.client))
        results = [insurance_document_payload(d, request=request) for d in insurance_docs]
        results.extend(dmv_document_payload(d, request=request) for d in dmv_docs)
        results.sort(key=lambda row: row.get("uploaded_at") or "", reverse=True)
        return Response({"count": len(results), "results": results})


class ClientDocumentFileView(ClientAppAPIView):
    def get(self, request, kind: str, document_id: int):
        kind = (kind or "").strip().lower()
        client = request.client
        if kind == "insurance":
            doc = (
                InsurancePolicyDocument.objects.filter(id=document_id, policy__client=client)
                .select_related("policy")
                .first()
            )
            if not doc or not doc.file:
                raise Http404("Document not found.")
            return FileResponse(doc.file.open("rb"), as_attachment=False, filename=doc.file.name.split("/")[-1])
        if kind == "dmv":
            doc = (
                ServiceDocument.objects.filter(
                    Q(vehicle__client=client) | Q(service_record__vehicle__client=client),
                    id=document_id,
                )
                .distinct()
                .first()
            )
            if not doc or not doc.file:
                raise Http404("Document not found.")
            return FileResponse(doc.file.open("rb"), as_attachment=False, filename=doc.file.name.split("/")[-1])
        raise Http404("Unknown document kind.")


class ClientPaymentsView(ClientAppAPIView):
    def get(self, request):
        rows = list(_client_payments(request.client)[:100])
        return Response({"count": len(rows), "results": [payment_payload(p) for p in rows]})


class ClientVehiclesView(ClientAppAPIView):
    def get(self, request):
        rows = build_client_vehicles(request.client)
        return Response({"count": len(rows), "results": rows})


class ClientReceiptsView(ClientAppAPIView):
    def get(self, request):
        rows = build_client_receipts(request.client, limit=100)
        return Response({"count": len(rows), "results": rows})


class ClientUpcomingView(ClientAppAPIView):
    def get(self, request):
        days = int(request.query_params.get("days") or 90)
        days = max(7, min(days, 365))
        items = build_upcoming_items(request.client, days=days)
        return Response({"count": len(items), "results": items})


class ClientAlertsView(ClientAppAPIView):
    def get(self, request):
        alerts = build_alerts(request.client)
        return Response({"count": len(alerts), "unread_count": len(alerts), "results": alerts})


class ClientChatMessagesView(ClientAppAPIView):
    def get(self, request):
        after_raw = (request.query_params.get("after_id") or "").strip()
        after_id = int(after_raw) if after_raw.isdigit() else 0
        mark_read_by_client(request.client)
        rows = list_chat_messages(request.client, after_id=after_id, limit=150)
        return Response(
            {
                "count": len(rows),
                "unread_count": unread_for_client(request.client),
                "results": [serialize_chat_message(m) for m in rows],
            }
        )

    def post(self, request):
        body = ""
        if hasattr(request, "data"):
            body = request.data.get("body") or request.data.get("message") or ""
        try:
            msg = post_client_message(request.client, body)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serialize_chat_message(msg), status=status.HTTP_201_CREATED)


class ClientChatWaitView(ClientAppAPIView):
    """Long-poll for new chat messages (realtime without WebSockets)."""

    def get(self, request):
        after_raw = (request.query_params.get("after_id") or "").strip()
        after_id = int(after_raw) if after_raw.isdigit() else 0
        try:
            timeout = int(request.query_params.get("timeout") or 12)
        except (TypeError, ValueError):
            timeout = 12
        timeout = max(3, min(timeout, 20))

        def _fresh(after: int):
            qs = list(
                ClientChatMessage.objects.filter(client=request.client, id__gt=after)
                .select_related("staff_user", "client")
                .order_by("id")[:40]
            )
            return [serialize_chat_message(m) for m in qs]

        items = _fresh(after_id)
        if items:
            mark_read_by_client(request.client)
            return Response(
                {
                    "has_new": True,
                    "results": items,
                    "newest_id": items[-1]["id"],
                    "unread_count": unread_for_client(request.client),
                }
            )

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            wait_client_wake(request.client.id, timeout=min(1.2, max(0.2, deadline - time.monotonic())))
            items = _fresh(after_id)
            if items:
                mark_read_by_client(request.client)
                return Response(
                    {
                        "has_new": True,
                        "results": items,
                        "newest_id": items[-1]["id"],
                        "unread_count": unread_for_client(request.client),
                    }
                )
        return Response(
            {
                "has_new": False,
                "results": [],
                "newest_id": after_id,
                "unread_count": unread_for_client(request.client),
            }
        )
