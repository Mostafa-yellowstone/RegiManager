"""Join Kintone CSV exports into one profile per unique column.

An existing profile is never copied. If the unique number, driver license,
or the same name and phone is already in the office, that profile is skipped
and only missing vehicles, transactions, and documents are added.
"""

import csv
import hashlib
import io
import os
import re
import sys
import tempfile
import threading
import uuid
import zipfile
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.db import close_old_connections, transaction
from django.utils import timezone
from django.utils.timezone import is_naive, make_aware
from openpyxl import load_workbook

from .models import Client, ClientNote, Organization, ServiceDocument, ServiceRecord, Vehicle

LINK_ALIASES = (
    "unique",
    "unique_id",
    "unique_key",
    "unique_column",
    "client_key",
    "client_number",
    "customer_number",
    "customer_id",
    "external_key",
    "link_key",
    "id_number",
)

DATE_FORMATS = (
    "%b %d, %Y %I:%M %p",
    "%b %d, %Y %I:%M:%S %p",
    "%B %d, %Y %I:%M %p",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y %I:%M %p",
    "%m/%d/%Y",
    "%Y-%m-%d",
    "%m-%d-%Y",
)
PREFERRED_LINKS = (
    "license_number",
    "driver_license",
    "dl_number",
    "dl",
) + LINK_ALIASES
SERVICE_TYPES = {key for key, _label in ServiceRecord.SERVICE_TYPES}


def header_key(value):
    text = str(value or "").strip().lower().replace("$", "")
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def cell_str(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, datetime):
        return value.strftime("%b %d, %Y %I:%M %p")
    return str(value).strip()


def pick(row, *names):
    compact = {}
    for key, value in row.items():
        compact.setdefault(str(key).replace("_", ""), value)
    for name in names:
        key = header_key(name)
        value = cell_str(row.get(key))
        if not value:
            value = cell_str(compact.get(key.replace("_", "")))
        if value:
            return value
    return ""


def normalize_key(value):
    return cell_str(value).strip()


def alnum(value):
    return re.sub(r"[^A-Za-z0-9]", "", cell_str(value)).upper()


def phone_digits(value):
    return "".join(ch for ch in cell_str(value) if ch.isdigit())


def tidy_name(part):
    part = cell_str(part)
    if part.isupper():
        return part.title()
    return part


def split_last_first_middle(full):
    parts = [tidy_name(part) for part in re.sub(r"\s+", " ", cell_str(full)).split(" ") if part]
    if not parts:
        return "", "", ""
    if len(parts) == 1:
        return parts[0], "Client", ""
    return parts[1], parts[0], " ".join(parts[2:])


def person_from_row(row):
    first = tidy_name(pick(row, "first_name", "first", "firstname"))
    last = tidy_name(pick(row, "last_name", "last", "lastname"))
    middle = tidy_name(pick(row, "middle_name", "middle", "middlename"))
    if first and last:
        return first, last, middle
    return split_last_first_middle(pick(row, "name", "full_name", "client_name", "customer_name", "client"))


def parse_when(value):
    if isinstance(value, datetime):
        return value
    text = cell_str(value)
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def parse_year(value):
    digits = re.sub(r"\D", "", cell_str(value))
    if len(digits) == 4 and digits.startswith(("19", "20")):
        return int(digits)
    return None


def parse_money(value):
    text = cell_str(value).replace("$", "").replace(",", "")
    if not text:
        return Decimal("0.00")
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0.00")


def split_filenames(value):
    names = []
    pattern = re.compile(
        r"[^\\/\n\r,;|\"']+\.(?:pdf|jpe?g|png|webp|heic|tiff?|docx?|xlsx?)",
        re.I,
    )
    for match in pattern.findall(cell_str(value)):
        name = os.path.basename(match.strip())
        if name:
            names.append(name)
    return names


def filenames_in_row(row):
    """File names come from the Attachments column on the same row, not a separate app."""
    found = []
    for key, value in row.items():
        if "attachment" not in key:
            continue
        found.extend(split_filenames(value))
    return found


def rows_from_upload(uploaded):
    if uploaded is None:
        return []
    name = (getattr(uploaded, "name", "") or "").lower()
    uploaded.seek(0)
    if name.endswith(".xlsx"):
        workbook = load_workbook(filename=uploaded, read_only=True, data_only=True)
        sheet = workbook.active
        grid = list(sheet.iter_rows(values_only=True))
        workbook.close()
        if not grid:
            return []
        headers = [header_key(cell) for cell in grid[0]]
        rows = []
        for raw in grid[1:]:
            row = {}
            for idx, key in enumerate(headers):
                if key and idx < len(raw):
                    row[key] = raw[idx]
            if any(cell_str(value) for value in row.values()):
                rows.append(row)
        return rows

    raw_bytes = uploaded.read()
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw_bytes.decode("latin-1")
    sample = text[:4096]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        delimiter = ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    rows = []
    for raw in reader:
        row = {header_key(key): value for key, value in raw.items() if key}
        if any(cell_str(value) for value in row.values()):
            rows.append(row)
    return rows


def find_header(rows, wanted):
    if not rows or not wanted:
        return None
    key = header_key(wanted)
    compact = key.replace("_", "")
    for header in rows[0].keys():
        if header == key or header.replace("_", "") == compact:
            return header
    return None


def resolve_link_header(rows, requested, other_rows=()):
    if not rows:
        raise ValueError("The clients file has no data rows.")
    pools = [rows, *[group for group in other_rows if group]]
    if requested:
        found = find_header(rows, requested)
        if not found:
            headers = ", ".join(sorted(rows[0].keys()))
            raise ValueError(f"Could not find a column named '{requested}'. Headers in the clients file: {headers}.")
        for group in pools[1:]:
            if find_header(group, found) is None:
                headers = ", ".join(sorted(group[0].keys()))
                raise ValueError(
                    f"The other file is missing '{requested}'. Use License Number on both sheets. Headers found: {headers}."
                )
        return found
    shared = set(rows[0].keys())
    for group in pools[1:]:
        shared &= set(group[0].keys())
    search_in = shared or set(rows[0].keys())
    for alias in PREFERRED_LINKS:
        for header in search_in:
            if header == header_key(alias) or header.replace("_", "") == header_key(alias).replace("_", ""):
                return header
    for header in search_in:
        if "license" in header:
            return header
    raise ValueError(
        "Put License Number on both the client sheet and the vehicle sheet. "
        f"Headers found: {', '.join(sorted(rows[0].keys()))}."
    )


def require_link_header(rows, link_header, label):
    if not rows:
        return
    if find_header(rows, link_header) is None:
        headers = ", ".join(sorted(rows[0].keys()))
        raise ValueError(
            f"The {label} file is missing the unique column '{link_header}'. "
            f"Use License Number on both sheets. Headers found: {headers}."
        )


def row_link_value(row, link_header):
    key = header_key(link_header)
    compact = key.replace("_", "")
    if key in row:
        return normalize_key(row.get(key))
    for header, value in row.items():
        if header.replace("_", "") == compact:
            return normalize_key(value)
    return ""


def classify_rows(rows):
    if not rows:
        return None
    headers = {key.replace("_", "") for key in rows[0].keys()}
    vehicle_marks = {"vin", "platenumber", "vehicleid", "vehicletype"}
    client_marks = {"phonenumber", "clientnumber", "dateofbirth", "applicanttype", "gender", "clientuid"}
    transaction_marks = {"transactiondate", "subtotalxpress", "subtotaldmv", "grandtotal", "terminalnumber", "outstanding"}
    if headers & transaction_marks:
        return "transactions"
    if headers & vehicle_marks and not (headers & client_marks):
        return "vehicles"
    if headers & client_marks and not (headers & vehicle_marks):
        return "clients"
    if headers & {"service", "servicetype", "transaction", "servicefee"}:
        return "transactions"
    if headers & vehicle_marks:
        return "vehicles"
    if headers & client_marks:
        return "clients"
    return None


class _Upload:
    def __init__(self, name, data):
        self.name = name
        self._buffer = io.BytesIO(data)

    def seek(self, offset, whence=0):
        return self._buffer.seek(offset, whence)

    def read(self, size=-1):
        return self._buffer.read(size)


def read_bundle(uploaded):
    """Split one zip into the client sheet, the vehicle sheet, and attachment files."""
    uploaded.seek(0)
    archive = zipfile.ZipFile(uploaded)
    index = {}
    client_rows = []
    vehicle_rows = []
    transaction_rows = []
    unknown = []
    for info in archive.infolist():
        if info.is_dir():
            continue
        base = os.path.basename(info.filename)
        if not base or base.startswith("."):
            continue
        lower = base.lower()
        if lower.endswith((".csv", ".xlsx")):
            rows = rows_from_upload(_Upload(base, archive.read(info.filename)))
            kind = classify_rows(rows)
            if kind == "clients":
                client_rows.extend(rows)
            elif kind == "vehicles":
                vehicle_rows.extend(rows)
            elif kind == "transactions":
                transaction_rows.extend(rows)
            elif rows:
                unknown.append(base)
            continue
        index.setdefault(lower, info.filename)
    return archive, index, client_rows, vehicle_rows, transaction_rows, unknown


def document_type_for(filename):
    lower = filename.lower()
    if "registration" in lower:
        return "registration"
    if "title" in lower:
        return "title"
    if "insurance" in lower:
        return "insurance_id"
    if "license" in lower:
        return "driver_license"
    if "mv82" in lower:
        return "mv82"
    return "other"


def service_type_for(label):
    text = cell_str(label).lower().replace("-", " ")
    key = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    if key in SERVICE_TYPES:
        return key
    if "motorcycle" in text and "reg" in text:
        return "motorcycle_registration"
    if "renew" in text:
        return "registration_renewal"
    if "title" in text:
        return "title_only"
    if "regist" in text:
        return "vehicle_registration"
    return "other"


class KintoneImporter:
    def __init__(self, organization, actor, link_header):
        self.organization = organization
        self.actor = actor
        self.link_header = link_header
        self.clients = {}
        self.by_name = {}
        self.files_for_key = {}
        self.motorcycle_keys = set()
        self.created_clients = 0
        self.skipped_clients = 0
        self.seen_client_ids = set()
        self.created_vehicles = 0
        self.skipped_vehicles = 0
        self.created_transactions = 0
        self.skipped_transactions = 0
        self.created_documents = 0
        self.skipped_documents = 0
        self.errors = []
        self._zip = None
        self._zip_index = {}
        self._license_index = None
        self._by_external = {}
        self._by_phone_name = {}
        self._vehicles_by_vin = None
        self._vehicles_by_plate = {}
        self._case_ids = set()

    def remember(self, key, client, created):
        self.clients[key] = client
        if client.pk in self.seen_client_ids:
            return
        self.seen_client_ids.add(client.pk)
        if created:
            self.created_clients += 1
        else:
            self.skipped_clients += 1

    def preload(self):
        """Load the office once so each spreadsheet row does not query the database."""
        self._by_external = {}
        self._license_index = {}
        self._by_phone_name = {}
        for candidate in Client.objects.filter(organization=self.organization):
            if candidate.external_key:
                self._by_external[candidate.external_key] = candidate
            if candidate.driver_license:
                self._license_index.setdefault(alnum(candidate.driver_license), candidate)
            phone = phone_digits(candidate.phone_number)
            if len(phone) >= 10 and candidate.first_name and candidate.last_name:
                self._by_phone_name[(candidate.first_name.upper(), candidate.last_name.upper(), phone[-10:])] = candidate
            self.index_name(candidate, {})
        self._vehicles_by_vin = {}
        self._vehicles_by_plate = {}
        for vehicle in Vehicle.objects.filter(client__organization=self.organization).select_related("client"):
            if vehicle.vin:
                self._vehicles_by_vin.setdefault(vehicle.vin.upper(), vehicle)
            if vehicle.plate_number:
                self._vehicles_by_plate[(vehicle.client_id, vehicle.plate_number.upper())] = vehicle
        self._case_ids = set(
            ServiceRecord.objects.filter(case_id__startswith="KT").values_list("case_id", flat=True)
        )

    def license_index(self):
        if self._license_index is None:
            self.preload()
        return self._license_index

    def find_existing(self, key, row):
        if self._license_index is None:
            self.preload()
        found = self._by_external.get(key)
        if found:
            return found
        license_values = {alnum(key)}
        license_number = pick(row, "driver_license", "dl", "dl_number", "license_number")
        if license_number:
            license_values.add(alnum(license_number))
        license_values.discard("")
        for value in license_values:
            found = self._license_index.get(value)
            if found is not None:
                return found
        phone = phone_digits(pick(row, "phone_number", "phone", "phone_no", "mobile", "tel"))
        first, last, _middle = person_from_row(row)
        if len(phone) >= 10 and first and last:
            return self._by_phone_name.get((first.upper(), last.upper(), phone[-10:]))
        return None

    def client_for(self, key, row):
        key = normalize_key(key)
        if not key:
            return None
        cached = self.clients.get(key)
        if cached is not None:
            return cached
        existing = self.find_existing(key, row)
        if existing is not None:
            if not existing.external_key:
                existing.external_key = key[:64]
                existing.save(update_fields=["external_key"])
                self._by_external[existing.external_key] = existing
            self.remember(key, existing, created=False)
            self.index_name(existing, row)
            return existing

        named = self.by_name.get(self.name_key(row))
        if named is not None:
            self.remember(key, named, created=False)
            self.index_name(named, row)
            return named

        first, last, middle = person_from_row(row)
        if not first or not last:
            self.errors.append(f"No name for unique number {key}, so that profile was skipped.")
            return None
        gender = pick(row, "gender", "sex").lower()
        if gender.startswith("m"):
            gender = "male"
        elif gender.startswith("f"):
            gender = "female"
        else:
            gender = ""
        state = pick(row, "state").upper()[:2]
        if state not in {code for code, _label in Client.US_STATES}:
            state = "NY"
        category = pick(row, "applicant_type", "category", "account_type", "client_type").lower()
        phone = phone_digits(pick(row, "phone_number", "phone", "phone_no", "mobile", "tel"))
        license_number = normalize_key(pick(row, "driver_license", "dl", "dl_number", "license_number")) or key
        created_at = parse_when(pick(row, "created_datetime", "created_at", "date_created", "datetime", "date"))
        born = parse_when(pick(row, "dob", "date_of_birth", "birthdate", "birth_date"))
        client = Client(
            organization=self.organization,
            first_name=first[:100],
            last_name=last[:100],
            middle_name=middle[:100],
            external_key=key[:64],
            driver_license=license_number[:50],
            phone_number=phone[:20],
            email=pick(row, "email", "email_address") or None,
            gender=gender or None,
            city=tidy_name(pick(row, "city"))[:100],
            state=state,
            zip_code=pick(row, "zip_code", "zip", "zipcode")[:10],
            county=tidy_name(pick(row, "county"))[:100],
            street_address=pick(row, "street_address", "street", "address")[:200],
            is_commercial=category in {"commercial", "business", "dealer"},
            dob=born.date() if born else None,
            source="walk_in",
        )
        if created_at is not None and is_naive(created_at):
            created_at = make_aware(created_at)
        with transaction.atomic():
            client.save()
            if created_at is not None:
                Client.objects.filter(pk=client.pk).update(created_at=created_at)
                client.created_at = created_at
        self.license_index()[alnum(client.driver_license)] = client
        if client.external_key:
            self._by_external[client.external_key] = client
        phone_key = phone_digits(client.phone_number)
        if len(phone_key) >= 10:
            self._by_phone_name[(client.first_name.upper(), client.last_name.upper(), phone_key[-10:])] = client
        self.remember(key, client, created=True)
        self.index_name(client, row)
        return client

    def name_key(self, row):
        full = pick(row, "client", "name", "full_name", "client_name", "customer_name")
        return re.sub(r"\s+", " ", full).strip().upper()

    def index_name(self, client, row):
        values = [
            self.name_key(row),
            re.sub(r"\s+", " ", f"{client.last_name} {client.first_name} {client.middle_name}").strip().upper(),
        ]
        for value in values:
            if value:
                self.by_name.setdefault(value, client)

    def note_files(self, key, row):
        names = filenames_in_row(row)
        bucket = self.files_for_key.setdefault(key, [])
        vin = pick(row, "vin", "vin_number").upper()
        plate = pick(row, "plate_number", "plate", "license_plate").upper()
        for name in names:
            bucket.append({"name": name, "vin": vin, "plate": plate})
            if "motorcycle" in name.lower():
                self.motorcycle_keys.add(key)

    def vehicle_for(self, client, row, create=True):
        vin = pick(row, "vin", "vin_number").upper()
        plate = pick(row, "plate_number", "plate", "license_plate").upper()
        record_number = pick(row, "vehicle_id", "record_number", "record_no", "record_id")
        if self._vehicles_by_vin is None:
            self.preload()
        if vin:
            other = self._vehicles_by_vin.get(vin)
            if other is not None and other.client_id != client.pk:
                if create:
                    self.errors.append(f"VIN {vin} already belongs to {other.client.name}, so it was skipped.")
                    self.skipped_vehicles += 1
                return None
            if other is not None:
                if create:
                    self.skipped_vehicles += 1
                return other
        elif plate:
            current = self._vehicles_by_plate.get((client.pk, plate))
            if current:
                if create:
                    self.skipped_vehicles += 1
                return current
        if not create:
            return None
        if not vin:
            vin = f"KT{re.sub(r'[^A-Z0-9]', '', (record_number or plate or client.external_key).upper())}"[:50]
            current = self._vehicles_by_vin.get(vin)
            if current:
                self.skipped_vehicles += 1
                return current
        plate_type_raw = pick(row, "plate_type").lower()
        explicit_type = pick(row, "vehicle_type", "body_type").lower()
        if "motor" in explicit_type or "motor" in plate_type_raw:
            vehicle_type = "motorcycle"
        elif explicit_type in {code for code, _label in Vehicle.VEHICLE_TYPES}:
            vehicle_type = explicit_type
        elif client.external_key in self.motorcycle_keys:
            vehicle_type = "motorcycle"
        else:
            vehicle_type = "passenger"
        if "motor" in plate_type_raw:
            plate_type = "motorcycle"
        elif plate_type_raw in {code for code, _label in Vehicle.PLATE_TYPES}:
            plate_type = plate_type_raw
        else:
            plate_type = "motorcycle" if vehicle_type == "motorcycle" else "personal"
        fuel = pick(row, "fuel_type", "fuel").lower()
        body = pick(row, "body_type").lower()
        reg_effective = parse_when(pick(row, "registration_effective_date", "reg_effective_date"))
        reg_expires = parse_when(pick(row, "registration_expiration_date", "reg_expiration_date"))
        ins_effective = parse_when(pick(row, "insurance_effective_date", "ins_effective_date"))
        ins_expires = parse_when(pick(row, "insurance_expiration_date", "ins_expiration_date"))
        vehicle = Vehicle(
            client=client,
            vin=vin[:50],
            is_legacy_vin=len(vin) != 17 or any(char in vin for char in "IOQ"),
            plate_number=plate[:50],
            year=parse_year(pick(row, "year", "model_year")),
            make=pick(row, "make", "brand")[:100],
            model=pick(row, "model")[:100],
            color=pick(row, "color", "colour")[:50],
            weight=pick(row, "weight", "gross_weight")[:50],
            cylinders=pick(row, "cylinders", "engine_cylinders")[:20],
            vehicle_type=vehicle_type,
            plate_type=plate_type,
            fuel_type=fuel if fuel in {code for code, _label in Vehicle.FUEL_TYPES} else "gas",
            body_type=body if body in {code for code, _label in Vehicle.BODY_TYPES} else None,
            insurance_company=pick(row, "insurance_company", "insurance", "carrier")[:150],
            registration_effective_date=reg_effective.date() if reg_effective else None,
            registration_expiration_date=reg_expires.date() if reg_expires else None,
            insurance_effective_date=ins_effective.date() if ins_effective else None,
            insurance_expiration_date=ins_expires.date() if ins_expires else None,
            vehicle_number=(record_number or "")[:50],
        )
        with transaction.atomic():
            vehicle.save()
        if vehicle.vin:
            self._vehicles_by_vin[vehicle.vin.upper()] = vehicle
        if vehicle.plate_number:
            self._vehicles_by_plate[(client.pk, vehicle.plate_number.upper())] = vehicle
        self.created_vehicles += 1
        return vehicle

    def client_for_transaction(self, row):
        vin = pick(row, "vin", "vin_number").upper()
        if vin:
            if self._vehicles_by_vin is None:
                self.preload()
            vehicle = self._vehicles_by_vin.get(vin)
            if vehicle is not None:
                return vehicle.client
        name = self.name_key(row)
        if name and name in self.by_name:
            return self.by_name[name]
        if len(name) >= 8 and " " in name:
            matches = []
            for stored, client in self.by_name.items():
                if stored.startswith(name) or name.startswith(stored):
                    if client not in matches:
                        matches.append(client)
            if len(matches) == 1:
                return matches[0]
        key = row_link_value(row, self.link_header)
        if key and key in self.clients:
            return self.clients[key]
        return None

    def add_transaction(self, client, row):
        label = pick(row, "service", "service_type", "transaction", "transaction_type", "description")
        xpress = parse_money(pick(row, "subtotal_xpress", "subtotalxpress", "processing_fee"))
        dmv = parse_money(pick(row, "subtotal_dmv", "subtotaldmv", "dmv_fee"))
        tax = parse_money(pick(row, "sales_tax", "salestax"))
        grand = parse_money(pick(row, "grand_total", "grandtotal", "total", "service_fee", "fee", "amount", "price"))
        paid = parse_money(pick(row, "payments", "paid_amount", "payment"))
        if not label and not any((xpress, dmv, tax, grand, paid)):
            return
        service_type = service_type_for(label) if label else "other"
        when = parse_when(pick(row, "transaction_date", "date", "created_datetime", "datetime"))
        terminal = pick(row, "terminal_number", "terminal")
        vin = pick(row, "vin", "vin_number").upper()
        sales_for_record = tax
        tax_note = ""
        if grand and abs((xpress + dmv) - grand) <= Decimal("0.02") and abs((xpress + dmv + tax) - grand) > Decimal("0.02"):
            sales_for_record = Decimal("0.00")
            if tax:
                tax_note = f" Sales tax listed on the sheet: {tax}."
        if not paid and grand:
            outstanding = parse_money(pick(row, "outstanding"))
            paid = grand - outstanding
        digest = hashlib.sha1(
            f"{self.organization.id}|{client.pk}|{vin}|{when}|{grand}|{terminal}|{xpress}|{dmv}".encode()
        ).hexdigest()[:16]
        case_id = f"KT{digest}"
        if case_id in self._case_ids or ServiceRecord.objects.filter(case_id=case_id).exists():
            self._case_ids.add(case_id)
            self.skipped_transactions += 1
            return
        vehicle = self.vehicle_for(client, row, create=False)
        if vehicle is None:
            vehicle = client.vehicles.order_by("id").first()
        if vehicle is None:
            vehicle = self.vehicle_for(client, row, create=True)
        if vehicle is None:
            return
        notes = "Imported from Kintone."
        if terminal:
            notes = f"{notes} Terminal {terminal}."
        if label and service_type == "other":
            notes = f"{notes} Service: {label}."
        notes = f"{notes}{tax_note}"
        outstanding_left = parse_money(pick(row, "outstanding")) if pick(row, "outstanding") else None
        record = ServiceRecord(
            organization=self.organization,
            handled_by=self.actor,
            vehicle=vehicle,
            service_type=service_type,
            processing_fee=xpress,
            dmv_fee=dmv,
            sales_tax=sales_for_record,
            paid_amount=paid,
            terminal_number=terminal[:80],
            transaction_date=when.date() if when else timezone.now().date(),
            status="completed" if outstanding_left == Decimal("0.00") or (grand and paid >= grand) else "pending",
            notes=notes.strip(),
            case_id=case_id,
            client_name=client.name,
            vin=vin,
        )
        with transaction.atomic():
            record.save()
        self._case_ids.add(case_id)
        self.created_transactions += 1

    def attach_files(self):
        for key, client in self.clients.items():
            missing = []
            for item in self.files_for_key.get(key, []):
                filename = item["name"]
                if ServiceDocument.objects.filter(
                    vehicle__client=client,
                    custom_name__iexact=filename[:150],
                ).exists():
                    self.skipped_documents += 1
                    continue
                stored_name = self._zip_index.get(filename.lower())
                if not stored_name:
                    missing.append(filename)
                    continue
                vehicle = None
                if item["vin"] or item["plate"]:
                    vehicle = self.vehicle_for(
                        client,
                        {"vin": item["vin"], "plate_number": item["plate"]},
                        create=False,
                    )
                if vehicle is None:
                    vehicle = client.vehicles.order_by("id").first()
                if vehicle is None:
                    missing.append(filename)
                    continue
                payload = self._zip.read(stored_name)
                document = ServiceDocument(
                    vehicle=vehicle,
                    document_type=document_type_for(filename),
                    custom_name=filename[:150],
                )
                safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", os.path.basename(filename))[:80] or "document"
                document.file.save(safe_name, ContentFile(payload), save=True)
                self.created_documents += 1
            if not missing:
                continue
            content = "Kintone files listed but not included in the zip: " + ", ".join(sorted(set(missing)))
            if not ClientNote.objects.filter(client=client, content=content).exists():
                ClientNote.objects.create(client=client, created_by=self.actor, content=content)

    def open_zip(self, uploaded):
        if uploaded is None:
            return
        uploaded.seek(0)
        self._zip = zipfile.ZipFile(uploaded)
        for info in self._zip.infolist():
            if info.is_dir():
                continue
            base = os.path.basename(info.filename)
            if not base or base.startswith("."):
                continue
            self._zip_index.setdefault(base.lower(), info.filename)

    def close(self):
        if self._zip is not None:
            self._zip.close()

    def result(self):
        return {
            "clients_created": self.created_clients,
            "clients_skipped": self.skipped_clients,
            "vehicles_created": self.created_vehicles,
            "vehicles_skipped": self.skipped_vehicles,
            "transactions_created": self.created_transactions,
            "transactions_skipped": self.skipped_transactions,
            "documents_created": self.created_documents,
            "documents_skipped": self.skipped_documents,
            "errors": self.errors[:40],
            "error_count": len(self.errors),
        }


def _consume_rows(importer, rows, kind):
    for index, row in enumerate(rows, start=2):
        if kind == "Transactions":
            try:
                client = importer.client_for_transaction(row)
                if client is None:
                    who = importer.name_key(row) or "this row"
                    vin = pick(row, "vin", "vin_number")
                    detail = f"{who}, VIN {vin}" if vin else who
                    importer.errors.append(f"Transactions row {index} ({detail}) did not match a profile.")
                    continue
                importer.add_transaction(client, row)
            except Exception as exc:
                importer.errors.append(f"Transactions row {index}: {exc}")
            continue
        key = row_link_value(row, importer.link_header)
        if not key:
            named = importer.by_name.get(importer.name_key(row))
            key = named.external_key if named is not None else ""
        if not key:
            importer.errors.append(f"{kind} row {index} has no License Number, so it was skipped.")
            continue
        try:
            importer.note_files(key, row)
            client = importer.client_for(key, row)
            if client is None:
                continue
            if kind == "Vehicles":
                importer.vehicle_for(client, row, create=True)
            elif kind == "Transactions":
                importer.add_transaction(client, row)
        except Exception as exc:
            importer.errors.append(f"{kind} row {index}: {exc}")


def import_kintone(
    *,
    organization,
    actor,
    clients_file=None,
    vehicles_file=None,
    transactions_file=None,
    documents_zip=None,
    link_column="",
):
    archive = None
    zip_index = {}
    bundled_clients = []
    bundled_vehicles = []
    bundled_transactions = []
    if documents_zip is not None:
        archive, zip_index, bundled_clients, bundled_vehicles, bundled_transactions, unknown = read_bundle(documents_zip)
        if unknown:
            raise ValueError(
                "Could not tell which sheet these files are: "
                + ", ".join(unknown)
                + ". Use the client export and the vehicle export."
            )
    client_rows = rows_from_upload(clients_file) + bundled_clients
    vehicle_rows = rows_from_upload(vehicles_file) + bundled_vehicles
    transaction_rows = rows_from_upload(transactions_file) + bundled_transactions
    if not client_rows:
        raise ValueError("The zip needs both files: the client sheet and the vehicle sheet.")
    link_header = resolve_link_header(client_rows, link_column, other_rows=(vehicle_rows,))
    require_link_header(vehicle_rows, link_header, "vehicles")

    importer = KintoneImporter(organization, actor, link_header)
    importer.preload()
    importer._zip = archive
    importer._zip_index = zip_index
    try:
        if archive is None:
            importer.open_zip(documents_zip)
        _consume_rows(importer, client_rows, "Clients")
        _consume_rows(importer, vehicle_rows, "Vehicles")
        _consume_rows(importer, transaction_rows, "Transactions")
        importer.attach_files()
        return importer.result()
    finally:
        importer.close()


def _job_cache_key(job_id):
    return f"kintone-import:{job_id}"


def kintone_import_status(job_id):
    if not job_id:
        return None
    try:
        return cache.get(_job_cache_key(job_id))
    except Exception:
        return None


def _remember_job(job_id, payload):
    try:
        cache.set(_job_cache_key(job_id), payload, timeout=60 * 60)
    except Exception:
        pass


class _PathUpload:
    def __init__(self, path, name):
        self.name = name
        self._file = open(path, "rb")

    def seek(self, offset, whence=0):
        return self._file.seek(offset, whence)

    def read(self, size=-1):
        return self._file.read(size)

    def tell(self):
        return self._file.tell()

    def seekable(self):
        return True

    def readable(self):
        return True

    def __getattr__(self, name):
        return getattr(self._file, name)

    def close(self):
        self._file.close()


def copy_uploaded_zip(uploaded):
    handle, path = tempfile.mkstemp(suffix=".zip")
    os.close(handle)
    with open(path, "wb") as stored:
        for chunk in uploaded.chunks():
            stored.write(chunk)
    return path


def _run_kintone_import_job(job_id, organization_id, user_id, bundle_path, bundle_name, link_column):
    from django.contrib.auth.models import User

    close_old_connections()
    upload = None
    try:
        organization = Organization.objects.get(pk=organization_id)
        actor = User.objects.get(pk=user_id)
        upload = _PathUpload(bundle_path, bundle_name)
        result = import_kintone(
            organization=organization,
            actor=actor,
            documents_zip=upload,
            link_column=link_column,
        )
        _remember_job(job_id, {"status": "done", "results": result})
    except Exception as exc:
        _remember_job(job_id, {"status": "error", "error": str(exc)})
    finally:
        if upload is not None:
            upload.close()
        if bundle_path and os.path.exists(bundle_path):
            os.remove(bundle_path)
        close_old_connections()


def start_kintone_import(organization_id, user_id, bundle_path, bundle_name, link_column):
    job_id = uuid.uuid4().hex
    _remember_job(job_id, {"status": "running"})
    args = (job_id, organization_id, user_id, bundle_path, bundle_name, link_column)
    if "test" in sys.argv:
        _run_kintone_import_job(*args)
        return job_id
    threading.Thread(target=_run_kintone_import_job, args=args, daemon=True).start()
    return job_id
