"""Google Photos Library API integration.

This package provides modules for authenticating with and accessing
the Google Photos Library API using the requests library.
"""

from .auth import GooglePhotosAuth
from .client import GooglePhotosClient

__all__ = ["GooglePhotosAuth", "GooglePhotosClient"]
