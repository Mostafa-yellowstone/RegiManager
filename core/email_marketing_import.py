"""Import Email Marketing CRM contacts from CSV or Excel."""

from __future__ import annotations

import csv
import io
from typing import BinaryIO

from openpyxl import load_workbook

CONTACT_FIELDS_MAP = {
    "name": ["name", "full_name", "contact_name", "client_name"],
    "address_line1": ["address_line1", "address1", "street", "street_address", "address"],
    "address_line2": ["address_line2", "address2", "suite", "apt", "apartment"],
    "address_line3": ["address_line3", "address3", "address_line_3"],
    "city": ["city"],
    "state": ["state"],
    "zip_code": ["zip_code", "zip", "zipcode", "postal_code"],
    "phone": ["phone", "phone_number", "mobile", "telephone"],
    "email": ["email", "email_address", "mail"],
    "website": ["website", "url", "web"],
    "notes": ["notes", "note", "comments"],
}


def _normalize_key(value) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _map_row(raw_row: dict) -> dict[str, str]:
    normalized = {_normalize_key(k): ("" if v is None else str(v).strip()) for k, v in raw_row.items()}
    mapped: dict[str, str] = {}
    for field, aliases in CONTACT_FIELDS_MAP.items():
        for alias in aliases:
            if alias in normalized and normalized[alias]:
                mapped[field] = normalized[alias]
                break
    return mapped


def _rows_from_csv(file_obj: BinaryIO) -> list[dict]:
    text = io.TextIOWrapper(file_obj, encoding="utf-8-sig", errors="replace")
    reader = csv.DictReader(text)
    return [dict(row) for row in reader]


def _rows_from_xlsx(file_obj: BinaryIO) -> list[dict]:
    wb = load_workbook(file_obj, read_only=True, data_only=True)
    sheet = wb.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(cell or "").strip() for cell in rows[0]]
    data = []
    for row in rows[1:]:
        if not any(row):
            continue
        data.append({headers[i]: row[i] for i in range(len(headers)) if headers[i]})
    return data


def parse_contact_import_file(uploaded_file) -> list[dict[str, str]]:
    filename = (getattr(uploaded_file, "name", "") or "").lower()
    if filename.endswith(".csv"):
        rows = _rows_from_csv(uploaded_file)
    elif filename.endswith((".xlsx", ".xlsm")):
        rows = _rows_from_xlsx(uploaded_file)
    else:
        raise ValueError("Upload a .csv or .xlsx file.")

    contacts = []
    for row in rows:
        mapped = _map_row(row)
        if mapped.get("name") or mapped.get("email"):
            if not mapped.get("name"):
                mapped["name"] = mapped.get("email", "Imported Contact")
            contacts.append(mapped)
    return contacts
