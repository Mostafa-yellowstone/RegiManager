"""SFTP framework: refuse production connect without a host key fingerprint."""

from __future__ import annotations

from .exceptions import TerminalConnectorError
from .models import Connection, SftpEndpoint, SftpFileJob


def assert_host_key_verified(endpoint: SftpEndpoint) -> None:
    if endpoint.connection.environment == Connection.Environment.PRODUCTION:
        if not (endpoint.host_key_fingerprint or "").strip():
            raise TerminalConnectorError(
                "Production SFTP requires a verified host key fingerprint."
            )


def record_inbound_file(endpoint: SftpEndpoint, filename: str, checksum: str = "") -> SftpFileJob:
    assert_host_key_verified(endpoint)
    if checksum:
        existing = SftpFileJob.objects.filter(endpoint=endpoint, checksum=checksum).first()
        if existing:
            existing.status = SftpFileJob.Status.DUPLICATE
            existing.save(update_fields=["status"])
            return existing
    return SftpFileJob.objects.create(
        endpoint=endpoint,
        filename=filename,
        checksum=checksum,
        status=SftpFileJob.Status.PENDING,
    )
