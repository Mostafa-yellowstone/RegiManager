"""Combine two client profiles in the same office into one."""

from django.db import IntegrityError, transaction
from django.db.models import ForeignKey

from .models import Client, ClientNote, ServiceRecord, Vehicle


class ClientMergeError(Exception):
    pass


_BLANK_FIELDS = (
    "middle_name",
    "ssn",
    "driver_license",
    "dob",
    "phone_number",
    "email",
    "gender",
    "business_name",
    "business_ein",
)

_ADDRESS_FIELDS = (
    "building_no",
    "street_address",
    "apartment",
    "city",
    "state",
    "zip_code",
    "county",
)

_RESIDENCE_FIELDS = (
    "residence_building_no",
    "residence_street_address",
    "residence_apartment",
    "residence_city",
    "residence_zip_code",
    "residence_county",
)


def _blank(value):
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _address_blank(client, fields, street_name):
    return _blank(getattr(client, street_name)) and _blank(getattr(client, fields[0]))


def _fill_blanks(keeper, source):
    for field in _BLANK_FIELDS:
        if _blank(getattr(keeper, field)) and not _blank(getattr(source, field)):
            setattr(keeper, field, getattr(source, field))

    if keeper.referral_id is None and source.referral_id:
        keeper.referral_id = source.referral_id

    if _address_blank(keeper, _ADDRESS_FIELDS, "street_address") and not _address_blank(
        source, _ADDRESS_FIELDS, "street_address"
    ):
        for field in _ADDRESS_FIELDS:
            setattr(keeper, field, getattr(source, field))

    if _address_blank(keeper, _RESIDENCE_FIELDS, "residence_street_address") and not _address_blank(
        source, _RESIDENCE_FIELDS, "residence_street_address"
    ):
        for field in _RESIDENCE_FIELDS:
            setattr(keeper, field, getattr(source, field))

    if source.is_commercial and not keeper.is_commercial:
        keeper.is_commercial = True

    if not keeper.mv82_file and source.mv82_file:
        keeper.mv82_file = source.mv82_file.name

    if not keeper.app_pin_hash and source.app_pin_hash:
        keeper.app_pin_hash = source.app_pin_hash
        keeper.app_access_enabled = keeper.app_access_enabled or source.app_access_enabled


def _reassign_related(keeper, source):
    for rel in source._meta.related_objects:
        field = getattr(rel, "field", None)
        if getattr(rel, "many_to_many", False) or not isinstance(field, ForeignKey):
            continue
        model = rel.related_model
        manager = getattr(model, "all_objects", model._base_manager)
        row_ids = list(manager.filter(**{field.attname: source.pk}).values_list("pk", flat=True))
        for row_id in row_ids:
            try:
                with transaction.atomic():
                    manager.filter(pk=row_id).update(**{field.attname: keeper.pk})
            except IntegrityError:
                if model._meta.label_lower == "core.vehicle":
                    _fold_vehicle(keeper, manager.get(pk=row_id))
                else:
                    raise ClientMergeError(
                        f"Could not move {model._meta.verbose_name} onto the kept profile."
                    ) from None


def _fold_vehicle(keeper, vehicle):
    vin = (vehicle.vin or "").strip()
    clash = None
    if vin:
        clash = (
            Vehicle.all_objects.filter(client_id=keeper.pk, vin=vehicle.vin, deleted_at__isnull=True)
            .exclude(pk=vehicle.pk)
            .first()
        )
    if clash:
        if _blank(clash.plate_number) and not _blank(vehicle.plate_number):
            clash.plate_number = vehicle.plate_number
            clash.save(update_fields=["plate_number"])
        _reassign_related(clash, vehicle)
        vehicle.delete()
        return
    if not vin:
        vehicle.vin = f"MERGED-{vehicle.pk}"
    vehicle.client_id = keeper.pk
    vehicle.save(update_fields=["client_id", "vin"])


@transaction.atomic
def merge_clients(keeper, source, actor=None):
    """Move source records onto keeper, fill empty identity fields, and retire source."""
    if keeper.pk == source.pk:
        raise ClientMergeError("Choose two different profiles.")
    if keeper.organization_id != source.organization_id:
        raise ClientMergeError("Both profiles have to belong to the same office.")
    if keeper.deleted_at or source.deleted_at:
        raise ClientMergeError("A deleted profile cannot be merged.")

    source_name = source.full_display_name or source.name
    source_id = source.pk
    _fill_blanks(keeper, source)
    keeper.save()
    _reassign_related(keeper, source)

    ServiceRecord.all_objects.filter(vehicle__client=keeper).update(
        client_name=keeper.name,
        client_address=keeper.full_address,
    )

    who = ""
    if actor is not None and getattr(actor, "is_authenticated", False):
        who = actor.get_full_name() or actor.get_username()
    note = f"Merged profile {source_name} (#{source_id}) into this profile."
    if who:
        note = f"{note} Merged by {who}."
    note = (
        f"{note} Vehicles, insurance, DMV records, and notes from both profiles now live here "
        "for the whole office."
    )
    ClientNote.objects.create(client=keeper, created_by=actor if who else None, content=note)

    source.delete()
    return keeper
