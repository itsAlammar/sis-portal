"""Pluggable payment provider for training-course enrollments.

A single seam so the rest of the app never talks to a gateway directly.
- ManualProvider (default/MVP): no external call. Creates a payment intent
  that staff confirm manually (bank transfer / cash), matching the SIS
  fees model and PythonAnywhere's free-tier network limits.
- A real gateway (Moyasar / HyperPay / Tap ...) can implement the same
  `create_charge` / `verify` interface later without touching callers.

Selected via the `payment_provider` app-setting (defaults to "manual").
"""

import secrets
from typing import Optional


class ManualProvider:
    """Records a payment intent; actual settlement is confirmed by staff."""
    name = "manual"
    auto_settle = False   # staff must approve before access opens

    def create_charge(self, amount: float, description: str = "") -> str:
        """Return an opaque reference for this charge (no external call)."""
        return f"MAN-{secrets.token_hex(5).upper()}"

    def verify(self, reference: str) -> bool:
        """Manual charges are never auto-verified; staff approval settles them."""
        return False


_PROVIDERS = {"manual": ManualProvider}


def get_provider(name: Optional[str] = None):
    """Return the configured provider instance (defaults to manual)."""
    return _PROVIDERS.get((name or "manual"), ManualProvider)()
