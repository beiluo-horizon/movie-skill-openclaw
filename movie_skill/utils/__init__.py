"""Utility functions (HTTP retry, user-agent rotation)."""

from .retry import fetch_with_retry, MaxRetriesExceeded
from .user_agent import UserAgentManager

__all__ = ["fetch_with_retry", "MaxRetriesExceeded", "UserAgentManager"]
