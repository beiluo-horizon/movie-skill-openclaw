"""Site adapters for scraping Chinese media sites."""

from .base import SiteAdapter, SiteError
from .factory import create_adapter
from . import registry

# Register custom adapters
from .clm34 import Clm34Adapter
from .dygod import DygodAdapter
from .u3c3 import U3c3Adapter
registry.register("clm34", Clm34Adapter)
registry.register("dygod", DygodAdapter)
registry.register("u3c3", U3c3Adapter)

__all__ = ["SiteAdapter", "SiteError", "create_adapter", "registry"]
