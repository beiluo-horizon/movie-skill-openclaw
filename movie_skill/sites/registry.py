"""Registry for custom (non-generic) site adapters.

Custom adapters are for sites that need JS rendering, login/auth,
or complex multi-page scraping that the generic YAML-driven adapter
cannot handle.

Import custom adapter classes here to register them.
"""

from typing import Optional
from .base import SiteAdapter

# Registry of named adapter classes
_registry: dict[str, type[SiteAdapter]] = {}


def register(name: str, adapter_class: type[SiteAdapter]) -> None:
    """Register a custom adapter class for a site type name."""
    _registry[name] = adapter_class


def get(name: str) -> Optional[type[SiteAdapter]]:
    """Get an adapter class by type name. Returns None if not found."""
    return _registry.get(name)


def list_types() -> list[str]:
    """List all registered adapter type names."""
    return list(_registry.keys())
