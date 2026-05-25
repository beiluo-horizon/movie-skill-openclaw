"""Site adapter factory — creates adapters from YAML config."""

from typing import Any

from movie_skill.config.schema import SiteConfig
from .base import SiteAdapter
from . import registry


def create_adapter(site_name: str, site_config: dict[str, Any]) -> SiteAdapter:
    """Create a site adapter from YAML config dict.

    If the config has a 'type' field, load that named adapter class
    from the registry. Otherwise, use GenericAdapter (the default,
    config-driven adapter).

    Args:
        site_name: Unique name for this site (config key).
        site_config: Raw dict from sites.yaml for this site.

    Returns:
        A SiteAdapter instance.

    Raises:
        ValueError: If specified adapter type is not found in registry.
    """
    # Parse full config with Pydantic for validation
    parsed = SiteConfig(**site_config)

    adapter_type = parsed.type

    if adapter_type == "generic":
        from .generic import GenericAdapter
        return GenericAdapter(site_name, parsed)
    else:
        cls = registry.get(adapter_type)
        if cls is None:
            raise ValueError(
                f"Unknown adapter type '{adapter_type}' for site '{site_name}'. "
                f"Available types: generic, {', '.join(registry.list_types())}"
            )
        return cls(site_name, parsed)
