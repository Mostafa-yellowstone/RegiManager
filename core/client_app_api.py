"""Client mobile wallet API — end-customer access (not staff companion)."""

from __future__ import annotations

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
    client_profile_payload,
    dmv_document_payload,
    insurance_document_payload,
    policy_detail_payload,
    policy_list_item,
    schedule_payload,
)
from .insurance_policy_schedule import summarize_insurance_schedule
from .models import (
    InsurancePolicy,
    InsurancePolicyDocument,
    ServiceDocument,
)


class ClientAppAPIView(APIView):
    authentication_classes = [ClientAppAuthentication]
    permission_classes = [IsClientAppAuthenticated]


def _client_policies(client):
    return (
        InsurancePolicy.objects.filter(client=client)
        .select_related("insurance_company")
        .order_by("-created_at")
    )


def _client_dmv_documents(client):
    return (
        ServiceDocument.objects.filter(
            Q(vehicle__client=client) | Q(service_record__vehicle__client=client),
            document_type__in=("driver_license", "insurance_id"),
        )
        .select_related("vehicle", "service_record")
        .distinct()
        .order_by("-uploaded_at")
    )


def _client_insurance_documents(client, *, document_types=None):
    qs = InsurancePolicyDocument.objects.filter(policy__client=client).select_related("policy")
    if document_types:
        qs = qs.filter(document_type__in=document_types)
    return qs.order_by("-uploaded_at")


def _best_next_payment(client) -> dict | None:
    best = None
    for policy in _client_policies(client):
        summary = summarize_insurance_schedule(policy)
        due_date = summary.get("next_due_date")
        if not due_date:
            continue
        candidate = {
            "due_date": due_date.isoformat(),
            "amount": f"{summary['next_due_amount']:.2f}" if summary.get("next_due_amount") is not None else None,
            "policy_id": policy.id,
            "policy_number": policy.policy_number,
            "company": policy.insurance_company.name if policy.insurance_company_id else "",
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
        remaining_payments = 0
        for policy in policies:
            summary = summarize_insurance_schedule(policy)
            remaining_payments += summary["open"]

        id_cards = _client_insurance_documents(
            client, document_types=[InsurancePolicyDocument.DocumentType.ID_CARDS]
        )
        dmv_docs = _client_dmv_documents(client)

        return Response(
            {
                "client": client_profile_payload(client),
                "next_payment": _best_next_payment(client),
                "totals": {
                    "policies": len(policies),
                    "remaining_payments": remaining_payments,
                    "id_cards": id_cards.count(),
                    "dmv_documents": dmv_docs.count(),
                },
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
        return Response(policy_detail_payload(policy))


class ClientPolicyScheduleView(ClientAppAPIView):
    def get(self, request, policy_id: int):
        policy = _client_policies(request.client).filter(id=policy_id).first()
        if not policy:
            raise Http404("Policy not found.")
        return Response(schedule_payload(policy))


class ClientIdCardsView(ClientAppAPIView):
    def get(self, request):
        docs = list(
            _client_insurance_documents(
                request.client,
                document_types=[InsurancePolicyDocument.DocumentType.ID_CARDS],
            )
        )
        return Response(
            {
                "count": len(docs),
                "results": [insurance_document_payload(d, request=request) for d in docs],
            }
        )


class ClientDocumentsView(ClientAppAPIView):
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
                    document_type__in=("driver_license", "insurance_id"),
                )
                .distinct()
                .first()
            )
            if not doc or not doc.file:
                raise Http404("Document not found.")
            return FileResponse(doc.file.open("rb"), as_attachment=False, filename=doc.file.name.split("/")[-1])
        raise Http404("Unknown document kind.")
