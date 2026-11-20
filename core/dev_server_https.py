"""HTTPS for Django's development server only.

Production (gunicorn) never imports this. nginx keeps terminating TLS there.
"""

import datetime
import ipaddress
import ssl
import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import CommandError
from django.core.servers.basehttp import WSGIRequestHandler, WSGIServer

CERT_DIR = Path(settings.BASE_DIR) / "dev-certs"
CERT_FILE = CERT_DIR / "localhost.crt"
KEY_FILE = CERT_DIR / "localhost.key"
CA_FILE = CERT_DIR / "dev-ca.crt"
CA_KEY_FILE = CERT_DIR / "dev-ca.key"


def ensure_dev_certificate(cert_file=CERT_FILE, key_file=KEY_FILE, ca_file=None, ca_key_file=None):
    cert_file = Path(cert_file)
    key_file = Path(key_file)
    ca_file = Path(ca_file) if ca_file else cert_file.with_name("dev-ca.crt")
    ca_key_file = Path(ca_key_file) if ca_key_file else key_file.with_name("dev-ca.key")
    if cert_file.is_file() and key_file.is_file() and ca_file.is_file():
        # The CA is trusted locally, so its private key must not stay on disk.
        ca_key_file.unlink(missing_ok=True)
        return cert_file, key_file
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    except ImportError as exc:
        raise CommandError(
            "HTTPS on the development server needs the cryptography package, "
            "or set DEV_SERVER_HTTPS=False."
        ) from exc

    now = datetime.datetime.now(datetime.timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "RegiManager Development CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
        .issuer_name(ca_name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                    x509.IPAddress(ipaddress.IPv6Address("::1")),
                ]
            ),
            critical=False,
        )
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    cert_file.parent.mkdir(parents=True, exist_ok=True)

    def _write_key(path, private_key):
        path.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    _write_key(key_file, server_key)
    cert_file.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))
    ca_file.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    ca_key_file.unlink(missing_ok=True)
    return cert_file, key_file


def trust_dev_ca(ca_file=CA_FILE):
    """Trust the local CA in the current Windows user store. No effect on the production server."""
    if sys.platform != "win32":
        return False
    ca_file = Path(ca_file)
    if not ca_file.is_file():
        return False
    import subprocess

    result = subprocess.run(
        ["certutil", "-user", "-addstore", "Root", str(ca_file)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    output = f"{result.stdout}\n{result.stderr}"
    return result.returncode == 0 or "already in store" in output.lower()


class DevHTTPSRequestHandler(WSGIRequestHandler):
    def get_environ(self):
        environ = super().get_environ()
        # wsgiref turns this into wsgi.url_scheme=https, so Django treats the request as secure.
        environ["HTTPS"] = "on"
        return environ


class DevHTTPSWSGIServer(WSGIServer):
    certfile = None
    keyfile = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.RequestHandlerClass = DevHTTPSRequestHandler

    def server_bind(self):
        super().server_bind()
        if not self.certfile or not self.keyfile:
            raise CommandError("Development HTTPS certificate is missing.")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(self.certfile, self.keyfile)
        self.socket = context.wrap_socket(self.socket, server_side=True)
