"""Renewal autopilot and the Today board: cards for expiring policies, reminders, new terms."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import F, Min, Q, Sum
from django.utils import timezone
from django.utils.html import escape, linebreaks

from .insurance_producers import add_months
from .models import (
    Client,
    DailyPaymentTransaction,
    InsurancePolicy,
    InsurancePolicyDriver,
    InsurancePolicyInstallment,
    InsurancePolicyVehicle,
    InsuranceRenewal,
    InsuranceRenewalEvent,
    InsuranceRenewalSettings,
    OrganizationMembership,
)
from .role_permissions import is_owner_or_manager_role

logger = logging.getLogger(__name__)

OVERDUE_DAYS = 30
EXPIRING_BUCKETS = (7, 15, 30, 60)
TODAY_LIST_LIMIT = 6
CELEBRATION_DAYS = 7
PAYMENT_DUE_DAYS = 7
ZERO = Decimal("0.00")

Stage = InsuranceRenewal.Stage
Event = InsuranceRenewalEvent.Kind


def settings_for(organization) -> InsuranceRenewalSettings:
    obj, _ = InsuranceRenewalSettings.objects.get_or_create(organization=organization)
    return obj


def is_renewal_manager(user, membership) -> bool:
    if user.is_superuser:
        return True
    return bool(membership and is_owner_or_manager_role(membership.role))


def _local_today() -> date:
    return timezone.localdate()


def sync_renewals(organization, *, today: date | None = None) -> int:
    """Create cards for policies entering the window; keep open cards in step with their policy."""
    today = today or _local_today()
    window = settings_for(organization).window_days
    policies = list(
        InsurancePolicy.objects.filter(
            organization=organization,
            stage=InsurancePolicy.StageChoices.BOUND,
            status=InsurancePolicy.StatusChoices.ACTIVE,
            renewal__isnull=True,
            end_date__gte=today - timedelta(days=OVERDUE_DAYS),
            end_date__lte=today + timedelta(days=window),
        ).only("id", "end_date", "added_by_id")
    )
    InsuranceRenewal.objects.bulk_create(
        [
            InsuranceRenewal(
                organization=organization,
                policy=p,
                expiration_date=p.end_date,
                assigned_to_id=p.added_by_id,
            )
            for p in policies
        ],
        ignore_conflicts=True,
    )

    open_cards = InsuranceRenewal.objects.filter(organization=organization, stage__in=InsuranceRenewal.OPEN_STAGES)
    for card in open_cards.exclude(expiration_date=F("policy__end_date")).select_related("policy"):
        card.expiration_date = card.policy.end_date
        card.save(update_fields=["expiration_date", "updated_at"])
    now = timezone.now()
    for card in open_cards.exclude(policy__status=InsurancePolicy.StatusChoices.ACTIVE):
        card.stage = Stage.LOST
        card.lost_reason = InsuranceRenewal.LostReason.OTHER
        card.lost_note = "Policy was marked inactive."
        card.closed_at = now
        card.save(update_fields=["stage", "lost_reason", "lost_note", "closed_at", "updated_at"])
        log_event(card, Event.STAGE, None, "Closed as lost: the policy was marked inactive.")
    return len(policies)


def log_event(card, kind, user, note: str = "") -> InsuranceRenewalEvent:
    return InsuranceRenewalEvent.objects.create(renewal=card, kind=kind, user=user, note=note[:2000])


def scoped_cards(organization, user, *, mine: bool):
    cards = InsuranceRenewal.objects.filter(organization=organization).select_related(
        "policy", "policy__client", "policy__insurance_company", "assigned_to", "new_policy"
    )
    if mine:
        cards = cards.filter(assigned_to=user)
    return cards


def days_left(card, today: date) -> int:
    return (card.expiration_date - today).days


def reminder_due(card, offsets, today: date) -> int | None:
    """The reminder offset reached but not yet sent (None when nothing is due)."""
    if not card.is_open:
        return None
    left = days_left(card, today)
    sent = card.sent_offsets()
    reached = [o for o in offsets if left <= o and o not in sent]
    return min(reached) if reached else None


def mark_reminders_sent(card, today: date) -> None:
    left = days_left(card, today)
    offsets = settings_for(card.organization).reminder_offsets()
    sent = card.sent_offsets() | {o for o in offsets if left <= o}
    card.reminders_sent = ",".join(str(o) for o in sorted(sent, reverse=True))


# ── messages ────────────────────────────────────────────────────────────────


def message_values(card, user) -> dict:
    from .insurance_ledger_pdf import agency_branding

    policy = card.policy
    org = card.organization
    brand = agency_branding(org)
    brand["name"] = (getattr(org, "insurance_intake_display_name", "") or "").strip() or org.name
    agent_name = ""
    if user is not None:
        agent_name = (user.get_full_name() or user.get_username() or "").strip()
    return {
        "first_name": (policy.client.first_name or "").strip().title() or "there",
        "client_name": f"{policy.client.first_name} {policy.client.last_name}".strip(),
        "policy_number": policy.policy_number or "",
        "company": policy.insurance_company.name if policy.insurance_company else "insurance",
        "expiration_date": long_date(card.expiration_date),
        "premium": f"${policy.premium:,.2f}",
        "agent_name": agent_name or brand["name"],
        "agency_name": brand["name"],
        "agency_phone": brand["phone"] or "",
        "agency_email": brand["email"] or "",
    }


def long_date(d: date) -> str:
    return f"{d:%B} {d.day}, {d.year}"


def fill_template(template: str, values: dict) -> str:
    text = template or ""
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    return text


def email_problem(client) -> str:
    email = (client.email or "").strip()
    if not email:
        return "This client has no email address."
    try:
        validate_email(email)
    except ValidationError:
        return "This client's email address is not valid."
    return ""


def send_renewal_email(card, user, subject: str, body: str) -> str:
    """Send the reminder now; returns an error message ("" on success)."""
    from .email_branding import attach_brand_logo, email_brand_for_org, outbound_from_email, wrap_email_html

    client = card.policy.client
    problem = email_problem(client)
    if problem:
        return problem
    subject = " ".join((subject or "").split())[:180]
    body = (body or "").strip()
    if not subject or not body:
        return "Subject and message are required."

    brand = email_brand_for_org(card.organization)
    reply_to = [brand["email"]] if brand.get("email") else None

    def build(with_logo: bool):
        message = EmailMultiAlternatives(
            subject, body, outbound_from_email(), [client.email.strip()], reply_to=reply_to
        )
        html_brand = brand
        if not (with_logo and attach_brand_logo(message, brand)):
            html_brand = {**brand, "logo_bytes": b"", "logo_cid": "", "logo_data_uri": ""}
        message.attach_alternative(wrap_email_html(linebreaks(escape(body)), html_brand, logo_mode="cid"), "text/html")
        return message

    try:
        try:
            build(True).send(fail_silently=False)
        except Exception:
            logger.exception("Renewal email with logo failed; retrying without logo")
            build(False).send(fail_silently=False)
    except Exception:
        logger.exception("Renewal email failed for renewal %s", card.id)
        return "The email could not be sent. Check the mail settings and try again."

    today = _local_today()
    mark_reminders_sent(card, today)
    record_contact(card, user, Event.EMAIL, f"Emailed {client.email.strip()}: {subject}")
    card.save()
    return ""


def record_contact(card, user, kind, note: str = "") -> None:
    card.last_contacted_at = timezone.now()
    card.contact_count += 1
    if card.stage == Stage.UPCOMING:
        card.stage = Stage.CONTACTED
    log_event(card, kind, user, note)


# ── stage changes ───────────────────────────────────────────────────────────


def close_lost(card, user, reason: str, note: str = "") -> None:
    card.stage = Stage.LOST
    card.lost_reason = reason
    card.lost_note = (note or "").strip()[:500]
    card.closed_at = timezone.now()
    card.save()
    label = InsuranceRenewal.LostReason(reason).label
    log_event(card, Event.STAGE, user, f"Lost: {label}" + (f" — {card.lost_note}" if card.lost_note else ""))


def reopen(card, user) -> None:
    card.stage = Stage.CONTACTED if card.contact_count else Stage.UPCOMING
    card.lost_reason = ""
    card.lost_note = ""
    card.closed_at = None
    card.save()
    log_event(card, Event.STAGE, user, "Reopened")


def _decimal(value, default=None):
    raw = (str(value).strip() if value is not None else "").replace(",", "").replace("$", "")
    if raw == "":
        return default
    try:
        return Decimal(raw)
    except InvalidOperation:
        raise ValidationError("Enter a valid amount.")


@dataclass
class RenewalTerms:
    policy_number: str
    premium: Decimal
    company_id: int | None
    commission_rate: Decimal | None
    period_months: int
    start_date: date
    business_type: str
    copy_vehicles: bool = True


def default_terms(card) -> RenewalTerms:
    policy = card.policy
    period = policy.insurance_period_months or 6
    return RenewalTerms(
        policy_number=policy.policy_number,
        premium=policy.premium,
        company_id=policy.insurance_company_id,
        commission_rate=policy.commission_rate,
        period_months=period,
        start_date=policy.end_date,
        business_type=InsurancePolicy.BusinessTypeChoices.RENEWAL,
    )


def terms_from_post(card, post) -> RenewalTerms:
    terms = default_terms(card)
    terms.policy_number = (post.get("policy_number") or "").strip()[:100] or terms.policy_number
    premium = _decimal(post.get("premium"))
    if premium is None or premium < 0:
        raise ValidationError("Enter the new premium.")
    terms.premium = premium
    company = (post.get("insurance_company") or "").strip()
    terms.company_id = int(company) if company.isdigit() else None
    rate = _decimal(post.get("commission_rate"))
    if rate is not None and not (0 <= rate <= 100):
        raise ValidationError("Commission rate must be between 0 and 100.")
    terms.commission_rate = rate
    period = (post.get("period_months") or "").strip()
    if period.isdigit() and 1 <= int(period) <= 36:
        terms.period_months = int(period)
    start = (post.get("start_date") or "").strip()
    if start:
        try:
            terms.start_date = date.fromisoformat(start)
        except ValueError:
            raise ValidationError("Enter a valid start date.")
    if terms.company_id and terms.company_id != card.policy.insurance_company_id:
        terms.business_type = InsurancePolicy.BusinessTypeChoices.REWRITE
    if post.get("business_type") in {
        InsurancePolicy.BusinessTypeChoices.RENEWAL,
        InsurancePolicy.BusinessTypeChoices.REWRITE,
    }:
        terms.business_type = post.get("business_type")
    terms.copy_vehicles = post.get("copy_vehicles", "1") != "0"
    return terms


@transaction.atomic
def renew(card, user, terms: RenewalTerms) -> InsurancePolicy:
    """Create the next policy term, link it to the card, and close the card as won."""
    old = card.policy
    if terms.company_id and not old.organization.insurance_companies.filter(id=terms.company_id).exists():
        raise ValidationError("Pick a company from this office.")
    new = InsurancePolicy.objects.create(
        organization=old.organization,
        client=old.client,
        policy_number=terms.policy_number,
        insurance_company_id=terms.company_id,
        premium=terms.premium,
        commission_rate=terms.commission_rate,
        insurance_type=old.insurance_type,
        stage=InsurancePolicy.StageChoices.BOUND,
        status=InsurancePolicy.StatusChoices.ACTIVE,
        source=InsurancePolicy.SourceChoices.EXISTING_CLIENT,
        business_type=terms.business_type,
        bound_date=_local_today(),
        added_by=user,
        start_date=terms.start_date,
        end_date=add_months(terms.start_date, terms.period_months),
        insurance_period_months=terms.period_months,
        named_insured=old.named_insured,
        insured_address=old.insured_address,
        vin=old.vin,
        plate_number=old.plate_number,
        driver_name=old.driver_name,
        producer=old.producer,
        producer_rate=old.producer_rate,
        producer_rate_basis=old.producer_rate_basis,
        producer_payout=old.producer_payout,
    )
    if terms.copy_vehicles:
        InsurancePolicyVehicle.objects.bulk_create(
            [
                InsurancePolicyVehicle(
                    policy=new,
                    auto_number=v.auto_number,
                    year=v.year,
                    make=v.make,
                    vin=v.vin,
                    plate_number=v.plate_number,
                    effective_date=new.start_date,
                    expiration_date=new.end_date,
                )
                for v in old.policy_vehicles.all()
            ]
        )
        InsurancePolicyDriver.objects.bulk_create(
            [
                InsurancePolicyDriver(policy=new, name=d.name, effective_date=new.start_date, expiry_date=new.end_date)
                for d in old.policy_drivers.all()
            ]
        )

    won = Stage.REWRITTEN if terms.business_type == InsurancePolicy.BusinessTypeChoices.REWRITE else Stage.RENEWED
    card.stage = won
    card.new_policy = new
    card.closed_at = timezone.now()
    card.lost_reason = ""
    card.lost_note = ""
    card.save()
    log_event(
        card,
        Event.STAGE,
        user,
        f"{won.label}: new term {new.policy_number or '#' + str(new.id)} at ${new.premium:,.2f} "
        f"({new.start_date:%b %d, %Y} – {new.end_date:%b %d, %Y})",
    )
    return new


def linkable_policies(card):
    """Policies already entered for this client that could be the next term."""
    old = card.policy
    return (
        InsurancePolicy.objects.filter(
            organization=old.organization,
            client=old.client,
            stage=InsurancePolicy.StageChoices.BOUND,
            start_date__gte=old.start_date,
        )
        .exclude(id=old.id)
        .exclude(renewed_from__isnull=False)
        .select_related("insurance_company")
        .order_by("-start_date")
    )


@transaction.atomic
def link_existing(card, user, new_policy) -> None:
    rewrite = (
        new_policy.business_type == InsurancePolicy.BusinessTypeChoices.REWRITE
        or new_policy.insurance_company_id != card.policy.insurance_company_id
    )
    won = Stage.REWRITTEN if rewrite else Stage.RENEWED
    card.stage = won
    card.new_policy = new_policy
    card.closed_at = timezone.now()
    card.lost_reason = ""
    card.lost_note = ""
    card.save()
    log_event(card, Event.STAGE, user, f"{won.label}: linked policy {new_policy.policy_number or '#' + str(new_policy.id)}")


def renewal_history(policy) -> list[InsurancePolicy]:
    """Every term in this policy's renewal chain, oldest first."""
    chain = [policy]
    seen = {policy.id}
    current = policy
    while True:
        prev = InsuranceRenewal.objects.filter(new_policy=current).select_related("policy").first()
        if prev is None or prev.policy_id in seen:
            break
        chain.insert(0, prev.policy)
        seen.add(prev.policy_id)
        current = prev.policy
    current = policy
    while True:
        try:
            card = current.renewal
        except InsuranceRenewal.DoesNotExist:
            card = None
        if card is None or card.new_policy_id is None or card.new_policy_id in seen:
            break
        chain.append(card.new_policy)
        seen.add(card.new_policy_id)
        current = card.new_policy
    return chain


# ── retention ───────────────────────────────────────────────────────────────


@dataclass
class RetentionRow:
    label: str
    due: int = 0
    won: int = 0
    lost: int = 0
    open: int = 0
    kept_premium: Decimal = ZERO
    lost_premium: Decimal = ZERO

    @property
    def closed(self) -> int:
        return self.won + self.lost

    @property
    def rate(self) -> int | None:
        return round(self.won * 100 / self.closed) if self.closed else None


@dataclass
class Retention:
    total: RetentionRow
    by_agent: list[RetentionRow] = field(default_factory=list)
    by_company: list[RetentionRow] = field(default_factory=list)
    by_month: list[RetentionRow] = field(default_factory=list)
    lost_reasons: list[tuple[str, int]] = field(default_factory=list)


def retention(cards) -> Retention:
    total = RetentionRow("All")
    agents: dict = {}
    companies: dict = {}
    months: dict = {}
    reasons: dict = {}

    def bump(row: RetentionRow, card):
        row.due += 1
        if card.stage in InsuranceRenewal.WON_STAGES:
            row.won += 1
            premium = card.new_policy.premium if card.new_policy_id else card.policy.premium
            row.kept_premium += premium or ZERO
        elif card.stage == Stage.LOST:
            row.lost += 1
            row.lost_premium += card.policy.premium or ZERO
        else:
            row.open += 1

    for card in cards:
        bump(total, card)
        agent = card.assigned_to
        agent_label = (agent.get_full_name() or agent.get_username()) if agent else "Unassigned"
        bump(agents.setdefault(agent_label, RetentionRow(agent_label)), card)
        company = card.policy.insurance_company.name if card.policy.insurance_company else "No company"
        bump(companies.setdefault(company, RetentionRow(company)), card)
        month_key = card.expiration_date.replace(day=1)
        bump(months.setdefault(month_key, RetentionRow(month_key.strftime("%b %Y"))), card)
        if card.stage == Stage.LOST:
            label = InsuranceRenewal.LostReason(card.lost_reason).label if card.lost_reason else "Not given"
            reasons[label] = reasons.get(label, 0) + 1

    def ordered(rows):
        return sorted(rows.values(), key=lambda r: (-r.due, r.label))

    return Retention(
        total=total,
        by_agent=ordered(agents),
        by_company=ordered(companies),
        by_month=[months[k] for k in sorted(months)],
        lost_reasons=sorted(reasons.items(), key=lambda kv: -kv[1]),
    )


# ── Today board ─────────────────────────────────────────────────────────────


def _phone_digits(phone: str) -> str:
    return "".join(ch for ch in (phone or "") if ch.isdigit() or ch == "+")


def _next_occurrence(month: int, day: int, today: date) -> date | None:
    for year in (today.year, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            candidate = date(year, 3, 1) if (month, day) == (2, 29) else None
        if candidate and candidate >= today:
            return candidate
    return None


def today_board(organization, user, *, mine: bool, today: date | None = None) -> dict:
    today = today or _local_today()
    sync_renewals(organization, today=today)
    settings = settings_for(organization)
    offsets = settings.reminder_offsets()

    open_cards = list(
        scoped_cards(organization, user, mine=mine)
        .filter(stage__in=InsuranceRenewal.OPEN_STAGES, policy__status=InsurancePolicy.StatusChoices.ACTIVE)
        .order_by("expiration_date", "id")
    )
    active_cards = [c for c in open_cards if not (c.snoozed_until and c.snoozed_until > today)]
    buckets = []
    for limit in EXPIRING_BUCKETS:
        buckets.append({"days": limit, "count": sum(1 for c in open_cards if 0 <= days_left(c, today) <= limit)})
    overdue = sum(1 for c in open_cards if days_left(c, today) < 0)
    expiring = []
    for card in active_cards[:TODAY_LIST_LIMIT]:
        expiring.append(
            {
                "card": card,
                "days_left": days_left(card, today),
                "days_over": max(-days_left(card, today), 0),
                "reminder_due": reminder_due(card, offsets, today),
                "phone": _phone_digits(card.policy.client.phone_number),
            }
        )

    policy_scope = Q(policy__organization=organization, policy__status=InsurancePolicy.StatusChoices.ACTIVE)
    if mine:
        policy_scope &= Q(policy__added_by=user)
    installments = list(
        InsurancePolicyInstallment.objects.filter(
            policy_scope, is_paid=False, due_date__lte=today + timedelta(days=PAYMENT_DUE_DAYS)
        )
        .select_related("policy", "policy__client", "policy__insurance_company")
        .order_by("due_date", "id")[:50]
    )
    missed = [i for i in installments if i.due_date < today]
    due_soon = [i for i in installments if i.due_date >= today]
    payments = [
        {
            "row": i,
            "missed": i.due_date < today,
            "days": (i.due_date - today).days,
            "phone": _phone_digits(i.policy.client.phone_number),
        }
        for i in (missed + due_soon)[:TODAY_LIST_LIMIT]
    ]

    collected_qs = DailyPaymentTransaction.objects.filter(organization=organization)
    today_total = collected_qs.filter(transaction_date=today).aggregate(t=Sum("amount"))["t"] or ZERO
    target = settings.daily_collection_target or ZERO
    target_label = "Daily goal"
    if target <= 0:
        week = collected_qs.filter(
            transaction_date__gte=today - timedelta(days=7), transaction_date__lt=today
        ).aggregate(t=Sum("amount"))["t"] or ZERO
        target = (week / 7).quantize(Decimal("0.01"))
        target_label = "Last 7-day average"
    percent = int(min(today_total * 100 / target, 999)) if target > 0 else None

    clients = Client.objects.filter(
        organization=organization,
        insurance_policies__stage=InsurancePolicy.StageChoices.BOUND,
        insurance_policies__status=InsurancePolicy.StatusChoices.ACTIVE,
    )
    if mine:
        clients = clients.filter(insurance_policies__added_by=user)
    clients = clients.annotate(since=Min("insurance_policies__bound_date")).distinct()
    celebrations = []
    horizon = today + timedelta(days=CELEBRATION_DAYS)
    for c in clients.only("id", "first_name", "last_name", "dob", "phone_number", "email"):
        if c.dob:
            when = _next_occurrence(c.dob.month, c.dob.day, today)
            if when and when <= horizon:
                celebrations.append({"client": c, "kind": "birthday", "date": when, "years": when.year - c.dob.year})
        if c.since:
            when = _next_occurrence(c.since.month, c.since.day, today)
            if when and when <= horizon and when.year - c.since.year >= 1:
                celebrations.append({"client": c, "kind": "anniversary", "date": when, "years": when.year - c.since.year})
    celebrations.sort(key=lambda r: (r["date"], r["client"].first_name))
    for row in celebrations:
        row["phone"] = _phone_digits(row["client"].phone_number)
        row["days"] = (row["date"] - today).days

    return {
        "buckets": buckets,
        "overdue": overdue,
        "expiring": expiring,
        "open_total": len(open_cards),
        "payments": payments,
        "missed_count": len(missed),
        "due_count": len(due_soon),
        "collected_today": today_total,
        "collection_target": target,
        "collection_target_label": target_label,
        "collection_percent": percent,
        "celebrations": celebrations[:TODAY_LIST_LIMIT],
        "celebration_total": len(celebrations),
        "mine": mine,
    }


def assignable_users(organization):
    return (
        OrganizationMembership.objects.filter(
            organization=organization, is_active=True, can_use_insurance=True
        )
        .select_related("user")
        .order_by("user__first_name", "user__last_name", "user__username")
    )
