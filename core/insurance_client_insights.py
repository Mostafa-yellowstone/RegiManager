"""Client 360: households, coverage gaps (cross-sell) and one merged activity timeline."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .insurance_producer_models import InsurancePolicyPremiumChange
from .models import (
    Client,
    ClientNote,
    DailyPaymentTransaction,
    InsuranceCoverageGapStatus,
    InsuranceHousehold,
    InsuranceHouseholdDismissal,
    InsuranceHouseholdMember,
    InsurancePolicy,
    InsurancePolicyDocument,
    InsurancePolicyVehicle,
    InsuranceQuoteLead,
    InsuranceRenewal,
    InsuranceRenewalEvent,
    OrganizationMembership,
    ServiceRecord,
)

AUTO_TYPES = frozenset({"auto_personal", "motor_cycle"})
HOME_TYPES = frozenset({"home_owners", "ho3", "ho4", "ho6", "dwelling"})
COMMERCIAL_TYPES = frozenset(
    {"commercial_auto", "trucking", "contractors", "landscaping", "business_owners_policy", "dealer_plates"}
)
INSURABLE_VEHICLE_TYPES = frozenset({"passenger", "truck", "motorcycle", "bus", "moped", "dump"})
LAPSE_LOOKBACK_DAYS = 365
SUGGESTION_LIMIT = 5
VEHICLE_GAP_LIMIT = 5
TIMELINE_LIMIT = 200
ZERO = Decimal("0.00")

Relationship = InsuranceHouseholdMember.Relationship
GapStatus = InsuranceCoverageGapStatus.Status


def _digits(value) -> str:
    return re.sub(r"\D", "", value or "")


def type_label(insurance_type: str, default: str = "Policy") -> str:
    label = dict(InsurancePolicy.INSURANCE_TYPE_CHOICES).get(insurance_type, insurance_type or default)
    return " ".join(w if any(c.isdigit() for c in w) else w.capitalize() for w in label.replace("_", " ").split())


def _phone_key(value) -> str:
    digits = _digits(value)
    return digits[-10:] if len(digits) >= 10 else ""


def _address_key(client) -> str:
    building = re.sub(r"[^a-z0-9]", "", (client.building_no or "").lower())
    street = re.sub(r"[^a-z0-9]", "", (client.street_address or "").lower())
    zip5 = (client.zip_code or "").strip()[:5]
    if not (building and street and zip5):
        return ""
    return f"{building}|{street}|{zip5}"


def _active_policies_q(today: date) -> Q:
    return Q(
        stage=InsurancePolicy.StageChoices.BOUND,
        status=InsurancePolicy.StatusChoices.ACTIVE,
        end_date__gte=today,
    )


# ---------------------------------------------------------------- households


def household_for(client) -> InsuranceHousehold | None:
    member = InsuranceHouseholdMember.objects.filter(client=client).select_related("household").first()
    return member.household if member else None


def household_clients(client) -> list[Client]:
    household = household_for(client)
    if household is None:
        return [client]
    return [m.client for m in household.members.select_related("client")]


def _pair(a_id: int, b_id: int) -> tuple[int, int]:
    return (a_id, b_id) if a_id < b_id else (b_id, a_id)


def household_suggestions(client) -> list[dict]:
    """Clients in the same office who share this client's phone or street address."""
    phone = _phone_key(client.phone_number)
    address = _address_key(client)
    if not phone and not address:
        return []

    query = Q()
    if phone:
        query |= Q(phone_number__contains=phone[-4:])
    if address:
        query |= Q(zip_code__startswith=address.rsplit("|", 1)[1], building_no__iexact=client.building_no.strip())
    candidates = (
        Client.objects.filter(organization_id=client.organization_id)
        .filter(query)
        .exclude(id=client.id)
        .order_by("-created_at")[:200]
    )

    own_household = household_for(client)
    dismissed = {
        _pair(low, high)
        for low, high in InsuranceHouseholdDismissal.objects.filter(
            Q(client_low=client) | Q(client_high=client)
        ).values_list("client_low_id", "client_high_id")
    }
    taken = {
        m.client_id: m.household_id
        for m in InsuranceHouseholdMember.objects.filter(client__in=[c.id for c in candidates])
    }

    out = []
    for other in candidates:
        if _pair(client.id, other.id) in dismissed:
            continue
        if own_household and taken.get(other.id) == own_household.id:
            continue
        reasons = []
        if phone and _phone_key(other.phone_number) == phone:
            reasons.append("Same phone")
        if address and _address_key(other) == address:
            reasons.append("Same address")
        if not reasons:
            continue
        out.append({"client": other, "reasons": reasons, "household_id": taken.get(other.id)})
        if len(out) >= SUGGESTION_LIMIT:
            break
    return out


def _household_name(client) -> str:
    last = (client.last_name or "").strip()
    if client.is_commercial and client.business_name:
        return client.business_name[:160]
    return f"{last} household"[:160] if last else f"{client.name} household"[:160]


@transaction.atomic
def link_household(client, other, *, relationship: str, user) -> InsuranceHousehold:
    """Put `other` in `client`'s household, creating one (client as primary) when needed."""
    if other.organization_id != client.organization_id or other.id == client.id:
        raise ValueError("Pick another client from this office.")
    if relationship not in Relationship.values:
        relationship = Relationship.OTHER

    household = household_for(client)
    other_household = household_for(other)
    if household is None and other_household is not None:
        household = other_household
        InsuranceHouseholdMember.objects.create(
            household=household, client=client, relationship=Relationship.OTHER, added_by=user
        )
        return household
    if household is None:
        household = InsuranceHousehold.objects.create(
            organization=client.organization, name=_household_name(client), created_by=user
        )
        InsuranceHouseholdMember.objects.create(
            household=household, client=client, relationship=Relationship.PRIMARY, added_by=user
        )
    if other_household is not None and other_household.id != household.id:
        InsuranceHouseholdMember.objects.filter(household=other_household).update(household=household)
        other_household.delete()
        InsuranceHouseholdMember.objects.filter(client=other).update(relationship=relationship)
    elif other_household is None:
        InsuranceHouseholdMember.objects.create(
            household=household, client=other, relationship=relationship, added_by=user
        )
    else:
        InsuranceHouseholdMember.objects.filter(client=other).update(relationship=relationship)
    return household


@transaction.atomic
def unlink_household(member_client) -> None:
    member = InsuranceHouseholdMember.objects.filter(client=member_client).select_related("household").first()
    if member is None:
        return
    household = member.household
    member.delete()
    remaining = list(household.members.all())
    if len(remaining) <= 1:
        household.delete()
    elif not any(m.relationship == Relationship.PRIMARY for m in remaining):
        first = remaining[0]
        first.relationship = Relationship.PRIMARY
        first.save(update_fields=["relationship"])


def dismiss_suggestion(client, other, user) -> None:
    low, high = _pair(client.id, other.id)
    InsuranceHouseholdDismissal.objects.get_or_create(
        client_low_id=low,
        client_high_id=high,
        defaults={"organization_id": client.organization_id, "dismissed_by": user},
    )


@dataclass
class HouseholdMemberRow:
    client: Client
    relationship: str
    relationship_label: str
    policy_count: int
    premium: Decimal
    is_current: bool


@dataclass
class HouseholdSummary:
    household: InsuranceHousehold
    members: list[HouseholdMemberRow]
    policy_count: int
    total_premium: Decimal
    next_expiration: date | None
    lines: list[str] = field(default_factory=list)


def household_summary(client, *, today: date | None = None) -> HouseholdSummary | None:
    household = household_for(client)
    if household is None:
        return None
    today = today or timezone.localdate()
    members = list(household.members.select_related("client"))
    policies = list(
        InsurancePolicy.objects.filter(_active_policies_q(today), client__in=[m.client_id for m in members])
    )
    rows = []
    for m in members:
        own = [p for p in policies if p.client_id == m.client_id]
        rows.append(
            HouseholdMemberRow(
                client=m.client,
                relationship=m.relationship,
                relationship_label=m.get_relationship_display(),
                policy_count=len(own),
                premium=sum((p.premium or ZERO for p in own), ZERO),
                is_current=m.client_id == client.id,
            )
        )
    rows.sort(key=lambda r: (r.relationship != Relationship.PRIMARY, not r.is_current, r.client.name.lower()))
    lines = sorted({type_label(p.insurance_type) for p in policies if p.insurance_type})
    return HouseholdSummary(
        household=household,
        members=rows,
        policy_count=len(policies),
        total_premium=sum((p.premium or ZERO for p in policies), ZERO),
        next_expiration=min((p.end_date for p in policies), default=None),
        lines=lines,
    )


# ---------------------------------------------------------------- coverage gaps


@dataclass
class CoverageGap:
    key: str
    title: str
    reason: str
    insurance_type: str
    tone: str = "info"
    status: str = ""
    lead: InsuranceQuoteLead | None = None
    vin: str = ""


def _vehicle_label(vehicle) -> str:
    bits = [str(vehicle.year or ""), vehicle.make, vehicle.model]
    label = " ".join(b for b in bits if b).strip()
    return label or vehicle.plate_number or vehicle.vin


def detect_gaps(client, *, today: date | None = None) -> list[CoverageGap]:
    today = today or timezone.localdate()
    family = household_clients(client)
    family_ids = [c.id for c in family]
    family_active = list(InsurancePolicy.objects.filter(_active_policies_q(today), client_id__in=family_ids))
    own_active = [p for p in family_active if p.client_id == client.id]
    family_types = {p.insurance_type for p in family_active}
    own_types = {p.insurance_type for p in own_active}
    gaps: list[CoverageGap] = []

    has_auto = bool(family_types & AUTO_TYPES)
    has_home = bool(family_types & HOME_TYPES)
    if has_auto and not has_home:
        gaps.append(
            CoverageGap(
                key="home",
                title="Home or renters",
                reason="Has auto with us but no home, condo or renters policy.",
                insurance_type="ho4",
                tone="good",
            )
        )

    auto_policy_ids = [p.id for p in family_active if p.insurance_type in AUTO_TYPES]
    insured_vehicle_count = max(
        len(auto_policy_ids),
        InsurancePolicyVehicle.objects.filter(policy_id__in=auto_policy_ids).count(),
    )
    if "umbrella" not in family_types and (insured_vehicle_count >= 2 or (has_auto and has_home)):
        why = "Home and auto with us" if has_auto and has_home else f"{insured_vehicle_count} insured vehicles"
        gaps.append(
            CoverageGap(
                key="umbrella",
                title="Umbrella",
                reason=f"{why} and no umbrella to protect against large claims.",
                insurance_type="umbrella",
            )
        )

    covered_vins = {(p.vin or "").strip().upper() for p in own_active if p.vin}
    covered_plates = {(p.plate_number or "").strip().upper() for p in own_active if p.plate_number}
    for pv in InsurancePolicyVehicle.objects.filter(policy__in=own_active).only("vin", "plate_number"):
        if pv.vin:
            covered_vins.add(pv.vin.strip().upper())
        if pv.plate_number:
            covered_plates.add(pv.plate_number.strip().upper())
    covered_vins.discard("")
    covered_plates.discard("")
    vehicle_gaps = 0
    for vehicle in client.vehicles.all().order_by("-created_at"):
        if vehicle.vehicle_type not in INSURABLE_VEHICLE_TYPES:
            continue
        vin = (vehicle.vin or "").strip().upper()
        plate = (vehicle.plate_number or "").strip().upper()
        if (vin and vin in covered_vins) or (plate and plate in covered_plates):
            continue
        if vehicle.vehicle_type in {"motorcycle", "moped"}:
            ins_type = "motor_cycle"
        elif client.is_commercial or vehicle.plate_type == "commercial":
            ins_type = "commercial_auto"
        else:
            ins_type = "auto_personal"
        where = f" (plate {vehicle.plate_number})" if vehicle.plate_number else ""
        gaps.append(
            CoverageGap(
                key=f"vehicle:{vehicle.id}",
                title=f"Uninsured: {_vehicle_label(vehicle)}",
                reason=f"This vehicle{where} is on the profile but not on any active policy with us.",
                insurance_type=ins_type,
                tone="warn",
                vin=vin,
            )
        )
        vehicle_gaps += 1
        if vehicle_gaps >= VEHICLE_GAP_LIMIT:
            break

    lapsed = (
        InsurancePolicy.objects.filter(
            client=client,
            stage=InsurancePolicy.StageChoices.BOUND,
        )
        .filter(
            Q(end_date__lt=today, end_date__gte=today - timedelta(days=LAPSE_LOOKBACK_DAYS))
            | Q(
                status=InsurancePolicy.StatusChoices.INACTIVE,
                inactive_date__gte=today - timedelta(days=LAPSE_LOOKBACK_DAYS),
            )
        )
        .exclude(insurance_type="")
        .select_related("insurance_company")
        .order_by("-end_date")
    )
    won = set(
        InsuranceRenewal.objects.filter(policy__client=client, stage__in=InsuranceRenewal.WON_STAGES).values_list(
            "policy_id", flat=True
        )
    )
    seen_types = set()
    for policy in lapsed:
        if policy.insurance_type in own_types or policy.insurance_type in seen_types or policy.id in won:
            continue
        seen_types.add(policy.insurance_type)
        when = policy.inactive_date if policy.status == InsurancePolicy.StatusChoices.INACTIVE else policy.end_date
        company = f" with {policy.insurance_company.name}" if policy.insurance_company else ""
        gaps.append(
            CoverageGap(
                key=f"lapsed:{policy.id}",
                title=f"Win back: {type_label(policy.insurance_type)}",
                reason=f"Policy {policy.policy_number}{company} ended {when:%b %d, %Y} and was not renewed.",
                insurance_type=policy.insurance_type,
                tone="warn",
            )
        )

    is_business = client.is_commercial or bool(own_types & COMMERCIAL_TYPES)
    if is_business:
        if "general_liability" not in own_types:
            gaps.append(
                CoverageGap(
                    key="gl",
                    title="General liability",
                    reason="Business account without general liability with us.",
                    insurance_type="general_liability",
                )
            )
        if "workers_compensation" not in own_types:
            gaps.append(
                CoverageGap(
                    key="wc",
                    title="Workers compensation",
                    reason="Business account without workers compensation with us.",
                    insurance_type="workers_compensation",
                )
            )
    return gaps


def coverage_gaps(client, *, today: date | None = None) -> list[CoverageGap]:
    """Open gaps (dismissed ones hidden) with any quote already requested attached."""
    gaps = detect_gaps(client, today=today)
    statuses = {
        s.gap_key: s
        for s in InsuranceCoverageGapStatus.objects.filter(client=client).select_related("lead", "lead__assigned_to__user")
    }
    out = []
    for gap in gaps:
        status = statuses.get(gap.key)
        if status and status.status == GapStatus.DISMISSED:
            continue
        if status:
            gap.status = status.status
            gap.lead = status.lead
        out.append(gap)
    return out


def find_gap(client, gap_key: str) -> CoverageGap | None:
    return next((g for g in detect_gaps(client) if g.key == gap_key), None)


def dismiss_gap(client, gap_key: str, user, note: str = "") -> None:
    InsuranceCoverageGapStatus.objects.update_or_create(
        client=client,
        gap_key=gap_key,
        defaults={
            "organization_id": client.organization_id,
            "status": GapStatus.DISMISSED,
            "note": note[:300],
            "user": user,
        },
    )


def _client_agent(client) -> OrganizationMembership | None:
    """The agent on the client's most recent policy, when they can still take insurance leads."""
    policy = (
        InsurancePolicy.objects.filter(client=client, added_by__isnull=False)
        .order_by("-created_at")
        .only("added_by_id")
        .first()
    )
    if policy is None:
        return None
    return OrganizationMembership.objects.filter(
        organization_id=client.organization_id,
        user_id=policy.added_by_id,
        is_active=True,
        can_deal_with_insurance=True,
    ).first()


def create_gap_lead(client, gap: CoverageGap, user) -> InsuranceQuoteLead:
    from .insurance_quote_distribution import assign_lead, auto_distribute_lead
    from .insurance_quote_pipeline_views import _refresh_linked_task_description
    from .realtime import publish_org_quote_event

    with transaction.atomic():
        lead = InsuranceQuoteLead.objects.create(
            organization=client.organization,
            created_by=user,
            client_name=client.name[:200],
            phone=(client.phone_number or "")[:30],
            email=client.email or "",
            heard_about=InsuranceQuoteLead.HeardAbout.EXISTING_CLIENT,
            street_address=" ".join(p for p in (client.building_no, client.street_address) if p)[:200],
            apartment=(client.apartment or "")[:50],
            city=(client.city or "")[:100],
            state=(client.state or "NY")[:2],
            zip_code=(client.zip_code or "")[:10],
            insurance_type=gap.insurance_type,
            vin=gap.vin[:32],
            dl_number=(client.driver_license or "")[:40],
            date_of_birth=client.dob,
            notes=f"Coverage gap: {gap.title}. {gap.reason}",
            stage=InsuranceQuoteLead.Stage.ASSIGNED,
            assignment_mode=InsuranceQuoteLead.AssignmentMode.UNASSIGNED,
        )
        today = timezone.localdate()
        quote = InsurancePolicy.objects.create(
            organization=client.organization,
            client=client,
            policy_number=f"Q-{lead.id}",
            premium=ZERO,
            stage=InsurancePolicy.StageChoices.QUOTE,
            status=InsurancePolicy.StatusChoices.PENDING,
            insurance_type=gap.insurance_type[:30],
            source=InsurancePolicy.SourceChoices.EXISTING_CLIENT,
            business_type=InsurancePolicy.BusinessTypeChoices.NEW_BUSINESS,
            bound_date=today,
            start_date=today,
            end_date=today + timedelta(days=183),
            added_by=None,
            named_insured=client.name[:255],
            insured_address=client.full_address[:500],
            vin=gap.vin[:17],
            driver_name=client.name[:200],
        )
        lead.crm_policy = quote
        lead.save(update_fields=["crm_policy", "updated_at"])

        agent = _client_agent(client)
        if agent is not None:
            assign_lead(lead, agent, mode=InsuranceQuoteLead.AssignmentMode.MANUAL, actor=user)
        else:
            auto_distribute_lead(lead, actor=user)
        lead.refresh_from_db()
        InsurancePolicy.objects.filter(pk=quote.pk).update(
            client=client,
            added_by_id=lead.assigned_to.user_id if lead.assigned_to_id else None,
        )
        _refresh_linked_task_description(lead)
        InsuranceCoverageGapStatus.objects.update_or_create(
            client=client,
            gap_key=gap.key,
            defaults={
                "organization_id": client.organization_id,
                "status": GapStatus.QUOTED,
                "lead": lead,
                "user": user,
            },
        )

    publish_org_quote_event(
        client.organization_id,
        "quote_pipeline.changed",
        {"lead_id": lead.id, "stage": lead.stage, "assigned_to_id": lead.assigned_to_id, "reason": "created"},
    )
    return lead


# ---------------------------------------------------------------- timeline


@dataclass
class TimelineItem:
    at: datetime | date
    kind: str
    title: str
    detail: str = ""
    url: str = ""
    who: str = ""

    @property
    def sort_key(self) -> datetime:
        if isinstance(self.at, datetime):
            return timezone.localtime(self.at).replace(tzinfo=None) if timezone.is_aware(self.at) else self.at
        return datetime.combine(self.at, time(12, 0))

    @property
    def has_time(self) -> bool:
        return isinstance(self.at, datetime)


TIMELINE_KINDS = (
    ("policy", "Policies"),
    ("renewal", "Renewals"),
    ("payment", "Payments"),
    ("quote", "Quotes"),
    ("document", "Documents"),
    ("note", "Notes"),
    ("dmv", "DMV"),
)


def _who(user) -> str:
    if user is None:
        return ""
    return user.get_full_name() or user.username


def _money(value) -> str:
    return f"${(value or ZERO):,.2f}"


def client_timeline(client, *, include_dmv: bool, limit: int = TIMELINE_LIMIT) -> list[TimelineItem]:
    items: list[TimelineItem] = []
    policies = list(
        InsurancePolicy.objects.filter(client=client).select_related("insurance_company", "added_by")[:limit]
    )
    for p in policies:
        url = reverse("insurance-policy-detail", args=[p.id])
        kind_label = type_label(p.insurance_type)
        company = p.insurance_company.name if p.insurance_company else ""
        if p.stage == InsurancePolicy.StageChoices.QUOTE:
            items.append(TimelineItem(p.created_at, "quote", f"Quote opened: {kind_label}", company, url, _who(p.added_by)))
            continue
        items.append(
            TimelineItem(
                p.bound_date or p.created_at,
                "policy",
                f"Policy bound: {kind_label} #{p.policy_number}",
                " · ".join(b for b in (company, _money(p.premium), f"{p.start_date:%b %d, %Y} – {p.end_date:%b %d, %Y}") if b),
                url,
                _who(p.added_by),
            )
        )
        if p.status == InsurancePolicy.StatusChoices.INACTIVE and p.inactive_date:
            items.append(TimelineItem(p.inactive_date, "policy", f"Policy inactive: #{p.policy_number}", company, url))

    policy_ids = [p.id for p in policies]
    for change in (
        InsurancePolicyPremiumChange.objects.filter(policy_id__in=policy_ids)
        .select_related("policy", "changed_by")[:limit]
    ):
        items.append(
            TimelineItem(
                change.created_at,
                "policy",
                f"Premium changed on #{change.policy.policy_number}",
                f"{_money(change.old_premium)} → {_money(change.new_premium)}" + (f" · {change.note}" if change.note else ""),
                reverse("insurance-policy-detail", args=[change.policy_id]),
                _who(change.changed_by),
            )
        )

    for event in (
        InsuranceRenewalEvent.objects.filter(renewal__policy__client=client)
        .select_related("renewal", "renewal__policy", "user")
        .order_by("-created_at")[:limit]
    ):
        items.append(
            TimelineItem(
                event.created_at,
                "renewal",
                f"Renewal {event.get_kind_display().lower()}: #{event.renewal.policy.policy_number}",
                event.note,
                reverse("insurance-renewal-detail", args=[event.renewal_id]),
                _who(event.user),
            )
        )

    for tx in (
        DailyPaymentTransaction.objects.filter(client=client)
        .select_related("recorded_by", "insurance_company")
        .order_by("-transaction_date", "-created_at")[:limit]
    ):
        bits = [tx.get_payment_method_display(), tx.policy_number, tx.insurance_company.name if tx.insurance_company else ""]
        items.append(
            TimelineItem(
                tx.transaction_date,
                "payment",
                f"{tx.get_payment_type_display()} payment {_money(tx.amount)}",
                " · ".join(b for b in bits if b),
                "",
                _who(tx.recorded_by),
            )
        )

    lead_ids = set(
        InsuranceCoverageGapStatus.objects.filter(client=client, lead__isnull=False).values_list("lead_id", flat=True)
    )
    leads = InsuranceQuoteLead.objects.filter(
        Q(crm_policy__client=client) | Q(id__in=lead_ids)
    ).select_related("created_by", "assigned_to__user").distinct()[:limit]
    pipeline = reverse("insurance-pipeline")
    for lead in leads:
        owner = _who(lead.assigned_to.user) if lead.assigned_to_id else "Unassigned"
        items.append(
            TimelineItem(
                lead.created_at,
                "quote",
                f"Quote lead: {type_label(lead.insurance_type, 'Quote')}",
                f"{lead.get_stage_display()} · {owner}",
                pipeline,
                _who(lead.created_by),
            )
        )

    for doc in (
        InsurancePolicyDocument.objects.filter(policy__client=client)
        .select_related("policy", "uploaded_by")
        .order_by("-uploaded_at")[:limit]
    ):
        items.append(
            TimelineItem(
                doc.uploaded_at,
                "document",
                f"Document: {doc.title}",
                f"{doc.get_document_type_display()} · #{doc.policy.policy_number}",
                reverse("insurance-policy-detail", args=[doc.policy_id]),
                _who(doc.uploaded_by),
            )
        )

    if client.email:
        from .insurance_esign_models import InsuranceESignEnvelope

        for env in InsuranceESignEnvelope.objects.filter(
            organization_id=client.organization_id, signer_email__iexact=client.email
        ).select_related("created_by")[:limit]:
            items.append(
                TimelineItem(env.created_at, "document", f"E-sign sent: {env.title}", env.get_status_display(), "", _who(env.created_by))
            )
            if env.signed_at:
                items.append(TimelineItem(env.signed_at, "document", f"E-sign completed: {env.title}", env.signer_name))

    for note in ClientNote.objects.filter(client=client).select_related("created_by").order_by("-created_at")[:limit]:
        text = (note.content or "").strip()
        items.append(
            TimelineItem(
                note.created_at,
                "note",
                "Note" + (" (follow-up done)" if note.is_done else ""),
                text[:280] + ("…" if len(text) > 280 else ""),
                "",
                _who(note.created_by),
            )
        )

    if include_dmv:
        for rec in (
            ServiceRecord.objects.filter(vehicle__client=client)
            .select_related("handled_by")
            .order_by("-transaction_date", "-created_at")[:limit]
        ):
            service = dict(ServiceRecord.SERVICE_TYPES).get(rec.service_type, rec.service_type.replace("_", " ").title())
            items.append(
                TimelineItem(
                    rec.transaction_date or rec.created_at,
                    "dmv",
                    f"DMV: {service}",
                    " · ".join(b for b in (rec.plate_number, rec.get_status_display()) if b),
                    "",
                    _who(rec.handled_by),
                )
            )

    items.sort(key=lambda i: i.sort_key, reverse=True)
    return items[:limit]


def timeline_kinds(items: list[TimelineItem]) -> list[tuple[str, str, int]]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item.kind] = counts.get(item.kind, 0) + 1
    return [(key, label, counts[key]) for key, label in TIMELINE_KINDS if counts.get(key)]
