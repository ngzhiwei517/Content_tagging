"""Cloud Run entry point used by Uvicorn."""

from taggy_cloud.api import app

__all__ = ["app"]
