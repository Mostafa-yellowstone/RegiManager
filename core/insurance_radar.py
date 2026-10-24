"""DMV-to-insurance radar: scan DMV work for insurance opportunities, assign and close them."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Count, Max, Q
from django.urls import reverse
from django.utils import timezone

from .insurance_client_insights import INSURABLE_VEHICLE_TYPES
from .insurance_radar_models import InsuranceRadarItem
from .models import Client, InsurancePolicy, InsurancePolicyVehicle, ServiceRecord, Vehicle

Signal = InsuranceRadarItem.Signal
Status = InsuranceRadarItem.Status

REGISTRATION_TYPES = ("vehicle_registration", "new_plates", "transfer_plate", "motorcycle_registration")
NEW_REGISTRATION_DAYS = 30
OUTSIDE_EXPIRING_DAYS = 45
REGISTRATION_RENEWAL_DAYS = 30
SURRENDER_DAYS = 30
DMV_ONLY_ACTIVE_DAYS = 90
SKIPPED_RECORD_STATUSES = ("failed", "refund")
SUMMARY_LIST_LIMIT = 5


def radar_enabled(organization) -> bool:
    return bool(organization and organization.has_psb_portal and organization.has_insurance)


def _norm(value) -> str:
    return (value or "").strip().upper()


@dataclass
class _Coverage:
    vins: dict
    plates: dict
    active_clients: set
    ever_insured_clients: set

    def policy_for(self, vehicle) -> int | None:
        return self.vins.get(_norm(vehicle.vin)) or self.plates.get(_norm(vehicle.plate_number))


def _coverage(organization, today: date) -> _Coverage:
    active = InsurancePolicy.objects.filter(
        organization=organization,
        stage=InsurancePolicy.StageChoices.BOUND,
        status=InsurancePolicy.StatusChoices.ACTIVE,
        end_date__gte=today,
    )
    vins, plates, active_clients = {}, {}, set()
    for pid, client_id, vin, plate in active.values_list("id", "client_id", "vin", "plate_number"):
        active_clients.add(client_id)
        if _norm(vin):
            vins[_norm(vin)] = pid
        if _norm(plate):
            plates[_norm(plate)] = pid
    for pid, vin, plate in InsurancePolicyVehicle.objects.filter(policy__in=active).values_list(
        "policy_id", "vin", "plate_number"
    ):
        if _norm(vin):
            vins.setdefault(_norm(vin), pid)
        if _norm(plate):
            plates.setdefault(_norm(plate), pid)
    ever = set(
        InsurancePolicy.objects.filter(
            organization=organization, stage=InsurancePolicy.StageChoices.BOUND
        ).values_list("client_id", flat=True)
    )
    return _Coverage(vins=vins, plates=plates, active_clients=active_clients, ever_insured_clients=ever)


def _vehicle_label(vehicle) -> str:
    bits = [str(vehicle.year or ""), vehicle.make, vehicle.model]
    label = " ".join(b for b in bits if b).strip() or vehicle.vin
    return f"{label} ({vehicle.plate_number})" if vehicle.plate_number else label


def sync_radar(organization, *, today: date | None = None) -> int:
    """Create radar items for new signals. Existing items (any status) are never recreated."""
    if not radar_enabled(organization):
        return 0
    today = today or timezone.localdate()
    coverage = _coverage(organization, today)
    existing = InsuranceRadarItem.objects.filter(organization=organization)
    known_keys = set(existing.values_list("signal_key", flat=True))
    open_vehicles = set(existing.filter(status=Status.OPEN, vehicle__isnull=False).values_list("vehicle_id", flat=True))
    open_clients = set(existing.filter(status=Status.OPEN).values_list("client_id", flat=True))
    service_labels = dict(ServiceRecord.SERVICE_TYPES)
    found: list[InsuranceRadarItem] = []

    def add(item: InsuranceRadarItem):
        if item.signal_key in known_keys:
            return
        known_keys.add(item.signal_key)
        if item.vehicle_id:
            open_vehicles.add(item.vehicle_id)
        open_clients.add(item.client_id)
        found.append(item)

    records = (
        ServiceRecord.objects.filter(organization=organization, vehicle__isnull=False)
        .exclude(status__in=SKIPPED_RECORD_STATUSES)
        .select_related("vehicle")
    )

    registrations = records.filter(
        service_type__in=REGISTRATION_TYPES,
        transaction_date__gte=today - timedelta(days=NEW_REGISTRATION_DAYS),
    ).order_by("-transaction_date", "-id")
    for rec in registrations:
        vehicle = rec.vehicle
        if vehicle.deleted_at or vehicle.vehicle_type not in INSURABLE_VEHICLE_TYPES:
            continue
        if vehicle.id in open_vehicles or coverage.policy_for(vehicle):
            continue
        add(
            InsuranceRadarItem(
                organization=organization,
                client_id=vehicle.client_id,
                vehicle=vehicle,
                service_record=rec,
                signal=Signal.NEW_REGISTRATION,
                signal_key=f"new_reg:{rec.id}",
                signal_date=rec.transaction_date,
                reason=(
                    f"{service_labels.get(rec.service_type, 'Registration')} on {rec.transaction_date:%b %d, %Y} "
                    f"for {_vehicle_label(vehicle)}. No active policy with us."
                )[:300],
                referred_by_id=rec.handled_by_id,
            )
        )

    surrenders = records.filter(
        service_type="surrender_plates",
        transaction_date__gte=today - timedelta(days=SURRENDER_DAYS),
    ).order_by("-transaction_date", "-id")
    for rec in surrenders:
        policy_id = coverage.policy_for(rec.vehicle)
        if not policy_id:
            continue
        number = InsurancePolicy.objects.filter(id=policy_id).values_list("policy_number", flat=True).first()
        add(
            InsuranceRadarItem(
                organization=organization,
                client_id=rec.vehicle.client_id,
                vehicle=rec.vehicle,
                service_record=rec,
                policy_id=policy_id,
                signal=Signal.PLATES_SURRENDERED,
                signal_key=f"surrender:{rec.id}",
                signal_date=rec.transaction_date,
                reason=(
                    f"Plates surrendered on {rec.transaction_date:%b %d, %Y} for {_vehicle_label(rec.vehicle)} "
                    f"while policy #{number} is active. Cancel, replace the vehicle, or move the policy."
                )[:300],
                referred_by_id=rec.handled_by_id,
            )
        )

    vehicles = Vehicle.objects.filter(client__organization=organization, client__deleted_at__isnull=True)
    last_handler = {}

    def handler_for(vehicle_ids):
        missing = [v for v in vehicle_ids if v not in last_handler]
        if missing:
            for vid, uid in (
                ServiceRecord.objects.filter(vehicle_id__in=missing)
                .order_by("vehicle_id", "-transaction_date", "-id")
                .values_list("vehicle_id", "handled_by_id")
            ):
                last_handler.setdefault(vid, uid)

    outside = list(
        vehicles.filter(
            insurance_expiration_date__gte=today,
            insurance_expiration_date__lte=today + timedelta(days=OUTSIDE_EXPIRING_DAYS),
        ).exclude(insurance_company="")
    )
    handler_for([v.id for v in outside])
    for vehicle in sorted(outside, key=lambda v: v.insurance_expiration_date):
        if vehicle.id in open_vehicles or coverage.policy_for(vehicle):
            continue
        add(
            InsuranceRadarItem(
                organization=organization,
                client_id=vehicle.client_id,
                vehicle=vehicle,
                signal=Signal.OUTSIDE_EXPIRING,
                signal_key=f"outside:{vehicle.id}:{vehicle.insurance_expiration_date.isoformat()}",
                signal_date=vehicle.insurance_expiration_date,
                reason=(
                    f"{_vehicle_label(vehicle)} is insured with {vehicle.insurance_company} until "
                    f"{vehicle.insurance_expiration_date:%b %d, %Y}. Quote before it renews there."
                )[:300],
                referred_by_id=last_handler.get(vehicle.id),
            )
        )

    renewals = list(
        vehicles.filter(
            registration_expiration_date__gte=today,
            registration_expiration_date__lte=today + timedelta(days=REGISTRATION_RENEWAL_DAYS),
            vehicle_type__in=INSURABLE_VEHICLE_TYPES,
        ).exclude(client_id__in=coverage.active_clients)
    )
    handler_for([v.id for v in renewals])
    for vehicle in sorted(renewals, key=lambda v: v.registration_expiration_date):
        if vehicle.id in open_vehicles:
            continue
        add(
            InsuranceRadarItem(
                organization=organization,
                client_id=vehicle.client_id,
                vehicle=vehicle,
                signal=Signal.REGISTRATION_RENEWAL,
                signal_key=f"reg_renewal:{vehicle.id}:{vehicle.registration_expiration_date.isoformat()}",
                signal_date=vehicle.registration_expiration_date,
                reason=(
                    f"Registration for {_vehicle_label(vehicle)} expires "
                    f"{vehicle.registration_expiration_date:%b %d, %Y}. Client has no insurance with us."
                )[:300],
                referred_by_id=last_handler.get(vehicle.id),
            )
        )

    recent_clients = (
        records.filter(transaction_date__gte=today - timedelta(days=DMV_ONLY_ACTIVE_DAYS))
        .values("vehicle__client_id")
        .annotate(last=Max("transaction_date"), vehicles=Count("vehicle", distinct=True))
    )
    latest_handler = {}
    for client_id, uid in (
        records.filter(transaction_date__gte=today - timedelta(days=DMV_ONLY_ACTIVE_DAYS))
        .order_by("vehicle__client_id", "-transaction_date", "-id")
        .values_list("vehicle__client_id", "handled_by_id")
    ):
        latest_handler.setdefault(client_id, uid)
    for row in recent_clients:
        client_id = row["vehicle__client_id"]
        if client_id in coverage.ever_insured_clients or client_id in open_clients:
            continue
        count = row["vehicles"]
        add(
            InsuranceRadarItem(
                organization=organization,
                client_id=client_id,
                signal=Signal.DMV_ONLY,
                signal_key=f"dmv_only:{client_id}",
                signal_date=row["last"],
                reason=(
                    f"DMV client with {count} vehicle{'s' if count != 1 else ''}, last visit "
                    f"{row['last']:%b %d, %Y}. Never insured with us."
                ),
                referred_by_id=latest_handler.get(client_id),
            )
        )

    InsuranceRadarItem.objects.bulk_create(found, ignore_conflicts=True)
    return len(found)


def scoped_items(organization, user, *, manager: bool):
    items = InsuranceRadarItem.objects.filter(organization=organization).select_related(
        "client", "vehicle", "policy", "referred_by", "assigned_to", "closed_by"
    )
    return items if manager else items.filter(assigned_to=user)


def _notify_assigned(organization, assignee, count: int, by_user) -> None:
    from .models import Notification
    from .realtime import publish_user_event
    from .timezone_utils import local_label

    by = by_user.get_full_name() or by_user.username
    notif = Notification.objects.create(
        user=assignee,
        organization=organization,
        event_type="insurance_radar_assigned",
        level=Notification.Level.INFO,
        title="Radar lead assigned" if count == 1 else f"{count} radar leads assigned",
        message=f"{by} assigned you {count} insurance opportunit{'y' if count == 1 else 'ies'} from the DMV radar.",
        action_url=reverse("insurance-radar"),
    )
    unread = Notification.objects.filter(user=assignee, is_read=False).count()
    publish_user_event(
        assignee.id,
        "notification.created",
        {
            "id": notif.id,
            "title": notif.title,
            "message": notif.message,
            "level": notif.level,
            "event_type": notif.event_type,
            "action_url": notif.action_url,
            "open_url": reverse("open-notification", args=[notif.id]),
            "created_at": notif.created_at.isoformat() if notif.created_at else "",
            "created_label": local_label(notif.created_at),
            "unread_count": unread,
        },
    )


def assign(items, assignee, by_user) -> int:
    """Assign items (or unassign when ``assignee`` is None); the new assignee gets one bell notification."""
    now = timezone.now()
    changed = [i for i in items if i.assigned_to_id != (assignee.id if assignee else None)]
    for item in changed:
        item.assigned_to = assignee
        item.assigned_by = by_user
        item.assigned_at = now if assignee else None
        item.save(update_fields=["assigned_to", "assigned_by", "assigned_at", "updated_at"])
    if changed and assignee is not None and assignee.id != by_user.id:
        _notify_assigned(changed[0].organization, assignee, len(changed), by_user)
    return len(changed)


def close(item, user, *, status: str, won: bool = False, note: str = "") -> None:
    item.status = status
    item.won = bool(won) and status == Status.DONE
    if note:
        item.note = note[:4000]
    item.closed_at = timezone.now()
    item.closed_by = user
    item.save(update_fields=["status", "won", "note", "closed_at", "closed_by", "updated_at"])


def reopen(item) -> None:
    item.status = Status.OPEN
    item.won = False
    item.closed_at = None
    item.closed_by = None
    item.save(update_fields=["status", "won", "closed_at", "closed_by", "updated_at"])


def now_insured(items, organization, today: date | None = None) -> set[int]:
    """Ids of open items whose vehicle (or client, when there is no vehicle) is now insured with us."""
    coverage = _coverage(organization, today or timezone.localdate())
    out = set()
    for item in items:
        if item.signal == Signal.PLATES_SURRENDERED:
            continue
        if item.vehicle_id and item.vehicle is not None:
            if coverage.policy_for(item.vehicle):
                out.add(item.id)
        elif item.client_id in coverage.active_clients:
            out.add(item.id)
    return out


@dataclass
class ReferrerRow:
    user: object
    referred: int
    open: int
    won: int
    dismissed: int

    @property
    def rate(self) -> int | None:
        decided = self.referred - self.open
        return round(self.won * 100 / decided) if decided else None


def scoreboard(organization, *, since: date | None = None) -> list[ReferrerRow]:
    items = InsuranceRadarItem.objects.filter(organization=organization, referred_by__isnull=False)
    if since:
        items = items.filter(created_at__date__gte=since)
    rows = (
        items.values("referred_by")
        .annotate(
            referred=Count("id"),
            open=Count("id", filter=Q(status=Status.OPEN)),
            won=Count("id", filter=Q(won=True)),
            dismissed=Count("id", filter=Q(status=Status.DISMISSED)),
        )
        .order_by("-won", "-referred")
    )
    from django.contrib.auth import get_user_model

    users = get_user_model().objects.in_bulk([r["referred_by"] for r in rows])
    return [
        ReferrerRow(users[r["referred_by"]], r["referred"], r["open"], r["won"], r["dismissed"])
        for r in rows
        if r["referred_by"] in users
    ]


def radar_summary(organization, user, *, manager: bool, today: date | None = None) -> dict | None:
    if not radar_enabled(organization):
        return None
    today = today or timezone.localdate()
    sync_radar(organization, today=today)
    open_items = scoped_items(organization, user, manager=manager).filter(status=Status.OPEN)
    counts = dict(open_items.values_list("signal").annotate(n=Count("id")))
    return {
        "open_total": sum(counts.values()),
        "unassigned": open_items.filter(assigned_to__isnull=True).count() if manager else 0,
        "signals": [(key, label, counts.get(key, 0)) for key, label in Signal.choices if counts.get(key)],
        "items": list(open_items.order_by("signal_date", "id")[:SUMMARY_LIST_LIMIT]),
    }


def client_radar_items(client):
    if not radar_enabled(client.organization):
        return []
    return list(
        InsuranceRadarItem.objects.filter(client=client, status=Status.OPEN).select_related("vehicle", "assigned_to")
    )
