"""Fixed identity used by the single-workspace demo application.

Production deployments should replace this dependency with an authenticated
principal derived from the request (for example, from verified JWT claims).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    tenant: str
    subject: str
    groups: frozenset[str]
    admin: bool = False


_DEMO_PRINCIPAL = Principal(
    tenant="demo-workspace",
    subject="demo-admin",
    groups=frozenset({"workspace", "admins"}),
    admin=True,
)


def principal() -> Principal:
    """Return the shared administrator identity for the no-login demo."""
    return _DEMO_PRINCIPAL
