from django.conf import settings
from django.contrib.staticfiles.management.commands.runserver import Command as StaticfilesRunserver

from core.dev_server_https import CA_FILE, DevHTTPSWSGIServer, ensure_dev_certificate, trust_dev_ca


class Command(StaticfilesRunserver):
    def handle(self, *args, **options):
        self._dev_ca_trusted = False
        if settings.DEV_SERVER_HTTPS:
            cert_file, key_file = ensure_dev_certificate()
            try:
                self._dev_ca_trusted = trust_dev_ca(CA_FILE)
            except Exception:
                self._dev_ca_trusted = False
            DevHTTPSWSGIServer.certfile = str(cert_file)
            DevHTTPSWSGIServer.keyfile = str(key_file)
            self.server_cls = DevHTTPSWSGIServer
            self.protocol = "https"
        super().handle(*args, **options)

    def on_bind(self, server_port):
        super().on_bind(server_port)
        if self.protocol != "https":
            return
        if self._dev_ca_trusted:
            self.stdout.write(
                self.style.SUCCESS(
                    "Development server HTTPS is on for this machine only. The production server does not use it."
                )
            )
            return
        self.stdout.write(
            self.style.WARNING(
                "Development server HTTPS is on. If the browser warns about the certificate, "
                "continue once. The production server does not use this."
            )
        )
