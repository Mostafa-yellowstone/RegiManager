"""The login code is typed by a person in the Regi modal. Nothing here reads a mailbox."""


class OtpNotFound(Exception):
    """No code was entered in time, or the person cancelled."""
