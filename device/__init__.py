"""Device communication layer."""

from .serial_link import SerialLink, SerialLinkError, available_ports

__all__ = ["SerialLink", "SerialLinkError", "available_ports"]

# ConnectionController is imported from .connection directly; it is kept out of
# this list so the CLI can use the serial layer without pulling in Qt.
