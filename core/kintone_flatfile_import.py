"""Import records.csv + Attachments/ disk folder from a Kintone backup.

Unlike the zip-based import, this path:
  - accepts the CSV as a regular HTTP upload (small, ~268 KB)
  - reads attachment files directly from a directory on the server disk
    (suitable for multi-gigabyte attachment folders that cannot be zipped
    and uploaded through a browser)

Every client row is deduplicated by driver-licence number (Personal) or
business EIN (Commercial).  A second upload silently updates the profile
and skips files that are already stored in the database.

Background execution
--------------------
``start_flatfile_import()`` launches a daemon thread and returns a job_id
string immediately.  The caller can poll ``flatfile_import_status(job_id)``
(backed by Django's cache) to show progress.  Progress is written every
25 rows so the admin page stays responsive without hammering the cache.
"""

from __future__ import annotations

import io
import logging
import os
import re
import sys
import threading
import uuid

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.db import close_old_connections, transaction

from .kintone_import import (
    KintoneImporter,
    _job_cache_key,      # noqa: PLC2701  (private but same package)
    _remember_job,       # noqa: PLC2701
    alnum,
    cell_str,
    document_type_for,
    normalize_key,
    rows_from_upload,
)
from .models import ClientNote, Organization, ServiceDocument, Vehicle

logger = logging.getLogger(__name__)


# ── Column name mapping ─────────────────────────────────────────────────────
# records.csv uses Kintone-internal column names; map the post-header_key()
# version of each header to the alias that KintoneImporter's helpers expect.

_COL_MAP: dict[str, str] = {
    # Personal-name fields
    "first":             "first_name",
    "last":              "last_name",
    "middle":            "middle_name",
    # Unique identifiers (used as link keys)
    "licenseper":        "driver_license",    # personal DL number
    "licensecom":        "business_ein",      # commercial EIN / licence
    # Demographics
    "birth_date":        "birth_date",
    "g_dropdown":        "gender",
    "applicanttype":     "applicant_type",
    # Business
    "business":          "business_name",
    # Address components (assembled into street_address below)
    "build_no":          "_building_no",
    "street_ad":         "_street",
    "apart":             "_apartment",
    "zip":               "zip_code",
    "city":              "city",
    "state":             "state",
    "county":            "county",
    # Commercial address components (from Kintone Text_18-22, Drop_down_7-8)
    "text_18":           "_comm_building_no",
    "text_19":           "_comm_street",
    "text_20":           "_comm_apartment",
    "text_21":           "_comm_city",
    "drop_down_8":       "_comm_state",
    "text_22":           "_comm_zip_code",
    "drop_down_7":       "_comm_county",
    "text_23":           "_comm_email",
    # Contact
    "number":            "phone_number",       # personal phone (raw "Number")
    "number_2":          "_phone_alt",         # commercial phone fallback
    "email":             "email",
    # Attachment paths (newline-separated)
    "attachment":        "attachment",
    # Record metadata
    "record_number":     "record_number",
    "date_and_time":     "created_datetime",
    "created_datetime":  "created_datetime",
}


def _normalize_row(raw: dict) -> dict:
    """
    Translate records.csv column names to the aliases used by KintoneImporter.

    Also:
    - assembles building_no + street + apartment into street_address
    - fills phone_number from the commercial fallback when personal is blank
    - synthesises first_name / last_name for commercial rows so the importer
      can store them (it requires non-empty first + last)
    """
    out: dict[str, str] = {}
    for key, value in raw.items():
        mapped = _COL_MAP.get(key, key)
        if mapped == "_phone_alt":
            if not cell_str(out.get("phone_number", "")):
                out["phone_number"] = value
            continue
        # Never overwrite an already-set key with an empty value
        if mapped in out and not cell_str(value):
            continue
        out[mapped] = value

    # Assemble the full street address from the three split components
    building  = cell_str(out.pop("_building_no", "")).strip()
    street    = cell_str(out.pop("_street",      "")).strip()
    apartment = cell_str(out.pop("_apartment",   "")).strip()

    # Commercial address components
    comm_bld    = cell_str(out.pop("_comm_building_no", "")).strip()
    comm_str    = cell_str(out.pop("_comm_street",      "")).strip()
    comm_apt    = cell_str(out.pop("_comm_apartment",   "")).strip()
    comm_city   = cell_str(out.pop("_comm_city",        "")).strip()
    comm_state  = cell_str(out.pop("_comm_state",       "")).strip()
    comm_zip    = cell_str(out.pop("_comm_zip_code",    "")).strip()
    comm_county = cell_str(out.pop("_comm_county",      "")).strip()
    comm_email  = cell_str(out.pop("_comm_email",       "")).strip()

    applicant_type = cell_str(out.get("applicant_type", "")).strip().lower()
    biz = cell_str(out.get("business_name", "")).strip()
    is_comm = applicant_type == "commercial" or bool(biz)

    if is_comm:
        if comm_bld and not building:
            building = comm_bld
        if comm_str and not street:
            street = comm_str
        if comm_apt and not apartment:
            apartment = comm_apt
        if comm_city and not cell_str(out.get("city", "")):
            out["city"] = comm_city
        if comm_state and not cell_str(out.get("state", "")):
            out["state"] = comm_state
        if comm_zip and not cell_str(out.get("zip_code", "")):
            out["zip_code"] = comm_zip
        if comm_county and not cell_str(out.get("county", "")):
            out["county"] = comm_county
        if comm_email and not cell_str(out.get("email", "")):
            out["email"] = comm_email

    parts = [p for p in (building, street, apartment) if p]
    if parts:
        out["street_address"] = " ".join(parts)
    if building:
        out["_saved_building_no"] = building
    if apartment:
        out["_saved_apartment"] = apartment

    # Synthesise first/last for commercial rows so the importer can create the
    # record.  Convention: first_name="Commercial", last_name=business_name.
    if applicant_type == "commercial" and biz:
        if not cell_str(out.get("first_name", "")):
            out["first_name"] = "Commercial"
        if not cell_str(out.get("last_name", "")):
            out["last_name"] = biz

    return out


def _link_key(row: dict) -> str:
    """Return the unique client key from a normalised row."""
    applicant_type = cell_str(row.get("applicant_type", "")).lower().strip()
    if applicant_type == "commercial":
        key = normalize_key(row.get("business_ein", ""))
    else:
        key = normalize_key(row.get("driver_license", ""))
    # Fall back to Kintone's own record_number when no DL / EIN is present
    return key or normalize_key(row.get("record_number", ""))


def _attachment_paths(row: dict) -> list[str]:
    """Return the list of relative attachment paths declared in this row."""
    raw = cell_str(row.get("attachment", ""))
    if not raw:
        return []
    paths: list[str] = []
    for seg in re.split(r"[\r\n]+", raw):
        seg = seg.strip().strip(",;|")
        if seg and "." in seg:
            paths.append(seg)
    return paths


# ── Disk attachment store ───────────────────────────────────────────────────

class _DiskStore:
    """
    Provides lazy, indexed read access to a directory tree of attachment files.

    The root is the Attachments/ folder that contains Attachment-XXXX/
    sub-directories:

        C:\\KintoneBackup\\Attachments\\
            Attachment-3980\\
                DANIEL,CABRERA.pdf
                ...
            Attachment-3981\\
                ...
    """

    def __init__(self, root: str) -> None:
        self._root = root
        # lazy-built: lowercase basename → absolute path
        self._index: dict[str, str] = {}
        self._indexed = False

    def _build_index(self) -> None:
        if self._indexed:
            return
        for dirpath, _, filenames in os.walk(self._root):
            for fname in filenames:
                self._index.setdefault(fname.lower(), os.path.join(dirpath, fname))
        self._indexed = True

    def read(self, rel_path: str) -> bytes | None:
        """
        Return the bytes for *rel_path* (as it appears in the Attachment column)
        or ``None`` if the file cannot be found on disk.

        Resolution order:
        1. Direct join: root + rel_path   (fastest path, covers most cases)
        2. Basename lookup across the full tree (handles moved/renamed folders)
        """
        # 1 – Direct path
        direct = os.path.join(self._root, rel_path)
        if os.path.isfile(direct):
            with open(direct, "rb") as fh:
                return fh.read()
        # 2 – Basename fallback
        self._build_index()
        full = self._index.get(os.path.basename(rel_path).lower())
        if full and os.path.isfile(full):
            with open(full, "rb") as fh:
                return fh.read()
        return None


# ── Flatfile importer ───────────────────────────────────────────────────────

class FlatfileImporter:
    """
    Processes records.csv rows and disk attachments into RegiManager.

    Duplicate clients are detected (and merged/updated) by the inner
    ``KintoneImporter``; duplicate documents are detected by a (client_pk,
    lower_basename) set so that re-running the import is safe.
    """

    def __init__(
        self,
        organization,
        actor,
        *,
        attachments_dir: str | None = None,
    ) -> None:
        self._org = organization
        self._actor = actor
        self._store = _DiskStore(attachments_dir) if attachments_dir else None
        # KintoneImporter needs a link_header; "driver_license" is the canonical
        # choice for this CSV (it equals the link key for personal clients).
        self._imp = KintoneImporter(organization, actor, link_header="driver_license")
        self._imp.preload()

        self.created_docs:  int = 0
        self.skipped_docs:  int = 0
        self.extra_errors:  list[str] = []
        # Tracks (client_pk, lowercase_basename) pairs already processed
        self._doc_seen: set[tuple[int, str]] = set()

    # ── Vehicle helper ──────────────────────────────────────────────────────

    def _placeholder_vehicle(self, client) -> Vehicle:
        """Return the client's first vehicle; create a stub one if none exists."""
        existing = client.vehicles.order_by("id").first()
        if existing:
            return existing
        # Build a minimal VIN that is stable across re-runs so we never create
        # more than one stub per client.
        stub_vin = f"KT{alnum(client.external_key or str(client.pk))}"[:50]
        v = Vehicle(
            client=client,
            vin=stub_vin,
            is_legacy_vin=True,
            plate_number="",
            vehicle_type="passenger",
            plate_type="personal",
        )
        with transaction.atomic():
            v.save()
        return v

    # ── Document attachment ─────────────────────────────────────────────────

    def _attach_docs(self, client, attachment_paths: list[str]) -> None:
        """Upload each file in *attachment_paths* exactly once per client."""
        if not self._store or not attachment_paths:
            return

        vehicle = None  # resolve lazily – only when we have something to upload

        for rel_path in attachment_paths:
            basename = os.path.basename(rel_path)
            dedup_key = (client.pk, basename.lower())

            # In-memory dedup (same session)
            if dedup_key in self._doc_seen:
                self.skipped_docs += 1
                continue

            # Database dedup (prior sessions / re-runs)
            if ServiceDocument.objects.filter(
                vehicle__client=client,
                custom_name__iexact=basename[:150],
            ).exists():
                self._doc_seen.add(dedup_key)
                self.skipped_docs += 1
                continue

            # Read from disk
            payload = self._store.read(rel_path)
            if payload is None:
                self.extra_errors.append(f"Not found on disk: {rel_path}")
                continue

            if vehicle is None:
                vehicle = self._placeholder_vehicle(client)

            safe_name = re.sub(r"[^A-Za-z0-9._\-]+", "_", basename)[:80] or "document"
            doc = ServiceDocument(
                vehicle=vehicle,
                document_type=document_type_for(basename),
                custom_name=basename[:150],
            )
            doc.file.save(safe_name, ContentFile(payload), save=True)
            self._doc_seen.add(dedup_key)
            self.created_docs += 1

    # ── Row processing ──────────────────────────────────────────────────────

    def _process_row(self, index: int, raw: dict) -> None:
        norm = _normalize_row(raw)
        key = _link_key(norm)

        if not key:
            self.extra_errors.append(
                f"Row {index}: no unique key (driver licence / EIN / record number) – skipped."
            )
            return

        try:
            client = self._imp.client_for(key, norm)
        except Exception as exc:
            self.extra_errors.append(f"Row {index}: {exc}")
            return

        if client is None:
            return

        # Post-process: ensure business_name and business_ein are stored on commercial clients
        # (KintoneImporter.client_for does not set them from the CSV row).
        comm_updates: list[str] = []
        biz = cell_str(norm.get("business_name", "")).strip()
        if biz and client.is_commercial and not client.business_name:
            client.business_name = biz[:200]
            comm_updates.append("business_name")
        ein = cell_str(norm.get("business_ein", "")).strip()
        if ein and client.is_commercial and not client.business_ein:
            client.business_ein = ein[:20]
            comm_updates.append("business_ein")
        if client.is_commercial:
            for field in ("city", "state", "zip_code", "county"):
                val = cell_str(norm.get(field, "")).strip()
                if val and not getattr(client, field, None):
                    setattr(client, field, val)
                    comm_updates.append(field)
        if comm_updates:
            client.save(update_fields=comm_updates)

        # Also store building_no / apartment separately where the model supports it
        building  = cell_str(norm.get("_saved_building_no", "") or raw.get("build_no", "") or raw.get("building_no", "")).strip()
        apartment = cell_str(norm.get("_saved_apartment", "") or raw.get("apart", "") or raw.get("apartment", "")).strip()
        updates: list[str] = []
        if building and not client.building_no:
            client.building_no = building[:20]
            updates.append("building_no")
        if apartment and not client.apartment:
            client.apartment = apartment[:50]
            updates.append("apartment")
        if updates:
            client.save(update_fields=updates)

        # Record client intake notes / memo from Text_2 if present
        notes_text = cell_str(raw.get("text_2", "") or raw.get("Text_2", "")).strip()
        if notes_text and not ClientNote.objects.filter(client=client, content=notes_text).exists():
            ClientNote.objects.create(client=client, created_by=self._actor, content=notes_text)

        # Upload documents from disk
        self._attach_docs(client, _attachment_paths(norm))

    def run(self, rows: list[dict], *, job_id: str | None = None) -> None:
        """Process all rows; write progress to cache every 25 rows."""
        total = len(rows)
        for i, row in enumerate(rows, start=2):   # start=2 → skip header row
            self._process_row(i, row)
            if job_id and i % 25 == 0:
                _remember_job(job_id, {
                    "status": "running",
                    "progress": {"done": i - 1, "total": total},
                })

    def result(self) -> dict:
        inner = self._imp.result()
        return {
            "clients_created":   inner["clients_created"],
            "clients_skipped":   inner["clients_skipped"],
            "documents_created": self.created_docs,
            "documents_skipped": self.skipped_docs,
            "errors":            (inner["errors"] + self.extra_errors)[:60],
            "error_count":       inner["error_count"] + len(self.extra_errors),
        }


# ── Public entry point ──────────────────────────────────────────────────────

def import_kintone_records(
    *,
    organization,
    actor,
    csv_path: str,
    attachments_dir: str | None,
    link_column: str = "",
    job_id: str | None = None,
) -> dict:
    """
    Process one ``records.csv`` file together with its companion
    ``Attachments/`` directory and merge the data into *organization*.

    Parameters
    ----------
    organization    : Organization model instance
    actor           : User performing the import
    csv_path        : Absolute path to ``records.csv`` on the server
    attachments_dir : Absolute path to the ``Attachments/`` root directory,
                      or ``None`` to skip document upload
    link_column     : Unused – kept for API parity; the link key is
                      auto-detected from the applicant type.
    job_id          : When provided, live progress is written to the cache
                      under this key so the admin page can poll it.
    """
    with open(csv_path, "rb") as fh:
        data = fh.read()

    # Wrap the bytes in a file-like object that rows_from_upload() accepts
    class _Buf:
        name = "records.csv"

        def __init__(self, data: bytes) -> None:
            self._b = io.BytesIO(data)

        def seek(self, *a):   return self._b.seek(*a)
        def read(self, *a):   return self._b.read(*a)

    rows = rows_from_upload(_Buf(data))
    if not rows:
        raise ValueError("records.csv is empty or could not be parsed.")

    importer = FlatfileImporter(
        organization,
        actor,
        attachments_dir=attachments_dir,
    )
    importer.run(rows, job_id=job_id)
    return importer.result()


# ── Background job helpers ──────────────────────────────────────────────────

def flatfile_import_status(job_id: str) -> dict | None:
    """Return the cached status dict for *job_id*, or ``None``."""
    if not job_id:
        return None
    try:
        return cache.get(_job_cache_key(job_id))
    except Exception:
        return None


def _run_flatfile_job(
    job_id: str,
    organization_id: int,
    user_id: int,
    csv_path: str,
    attachments_dir: str | None,
    link_column: str,
    is_temp_csv: bool = False,
) -> None:
    """Worker function executed in the background thread."""
    from django.contrib.auth.models import User

    close_old_connections()
    try:
        org   = Organization.objects.get(pk=organization_id)
        actor = User.objects.get(pk=user_id)
        result = import_kintone_records(
            organization=org,
            actor=actor,
            csv_path=csv_path,
            attachments_dir=attachments_dir,
            link_column=link_column,
            job_id=job_id,
        )
        _remember_job(job_id, {"status": "done", "results": result})
    except Exception as exc:
        logger.exception("Flatfile Kintone import failed (job %s)", job_id)
        _remember_job(job_id, {"status": "error", "error": str(exc)})
    finally:
        # Only remove temporary uploaded CSV files, never direct server files
        if is_temp_csv and csv_path and os.path.exists(csv_path):
            try:
                os.remove(csv_path)
            except OSError:
                pass
        close_old_connections()


def start_flatfile_import(
    organization_id: int,
    user_id: int,
    csv_path: str,
    attachments_dir: str | None,
    link_column: str = "",
    is_temp_csv: bool = False,
) -> str:
    """
    Launch the import in a background thread and return a ``job_id``.

    The job_id can be passed to ``flatfile_import_status()`` to poll progress.
    During tests the import runs synchronously so assertions work normally.
    """
    job_id = uuid.uuid4().hex
    _remember_job(job_id, {"status": "running", "progress": {"done": 0, "total": 0}})
    args = (job_id, organization_id, user_id, csv_path, attachments_dir, link_column, is_temp_csv)
    if "test" in sys.argv:
        _run_flatfile_job(*args)
        return job_id
    threading.Thread(target=_run_flatfile_job, args=args, daemon=False).start()
    return job_id
