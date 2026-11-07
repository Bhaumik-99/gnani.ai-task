"""Backward-compatible shim; production uses app.risk.rules."""

from app.risk.rules import analyse_explicit_request

__all__ = ["analyse_explicit_request"]
