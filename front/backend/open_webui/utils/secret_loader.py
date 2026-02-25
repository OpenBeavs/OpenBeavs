"""
Google Secret Manager integration for Open WebUI.

This module provides a unified way to load secrets from either:
1. Google Secret Manager (production)
2. Environment variables / .env file (local development)

Usage:
    from open_webui.utils.secret_loader import get_secret
    
    # Will load from Secret Manager if USE_SECRET_MANAGER=true, otherwise from env
    database_url = get_secret("DATABASE_URL", "database-url")
"""

import os
import logging
from typing import Optional

log = logging.getLogger(__name__)

# Cache secrets in memory to avoid repeated API calls
_secret_cache = {}

# Flag to determine if we should use Secret Manager
USE_SECRET_MANAGER = os.environ.get("USE_SECRET_MANAGER", "false").lower() == "true"
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "osu-genesis-hub")


def _get_secret_from_manager(secret_id: str) -> Optional[str]:
    """
    Fetch a secret from Google Secret Manager.
    
    Args:
        secret_id: The ID of the secret in Secret Manager (e.g., "database-url")
        
    Returns:
        The secret value, or None if not found or error occurred
    """
    # Check cache first
    if secret_id in _secret_cache:
        return _secret_cache[secret_id]
    
    try:
        from google.cloud import secretmanager
        
        client = secretmanager.SecretManagerServiceClient()
        secret_name = f"projects/{GCP_PROJECT_ID}/secrets/{secret_id}/versions/latest"
        
        response = client.access_secret_version(request={"name": secret_name})
        secret_value = response.payload.data.decode("UTF-8")
        
        # Cache the secret
        _secret_cache[secret_id] = secret_value
        
        log.info(f"Loaded secret '{secret_id}' from Google Secret Manager")
        return secret_value
        
    except Exception as e:
        log.error(f"Failed to load secret '{secret_id}' from Secret Manager: {e}")
        return None


def get_secret(env_var_name: str, secret_id: Optional[str] = None, default: str = "") -> str:
    """
    Get a secret value from Secret Manager or environment variable.
    
    This function provides a unified interface for loading secrets:
    - In production (USE_SECRET_MANAGER=true): Loads from Google Secret Manager
    - In development (USE_SECRET_MANAGER=false): Loads from environment variables
    
    Args:
        env_var_name: The environment variable name (e.g., "DATABASE_URL")
        secret_id: The Secret Manager secret ID (e.g., "database-url"). 
                   If None, converts env_var_name to kebab-case
        default: Default value if secret not found
        
    Returns:
        The secret value
        
    Example:
        database_url = get_secret("DATABASE_URL", "database-url")
    """
    # If USE_SECRET_MANAGER is false, just use environment variable
    if not USE_SECRET_MANAGER:
        return os.environ.get(env_var_name, default)
    
    # Generate secret_id from env_var_name if not provided
    if secret_id is None:
        secret_id = env_var_name.lower().replace("_", "-")
    
    # Try to get from Secret Manager first
    secret_value = _get_secret_from_manager(secret_id)
    
    if secret_value is not None:
        return secret_value
    
    # Fallback to environment variable
    log.warning(
        f"Failed to load '{secret_id}' from Secret Manager, "
        f"falling back to environment variable '{env_var_name}'"
    )
    return os.environ.get(env_var_name, default)


def clear_cache():
    """Clear the secret cache. Useful for testing or forcing refresh."""
    global _secret_cache
    _secret_cache = {}
    log.info("Secret cache cleared")


# Convenience functions for commonly used secrets
def get_database_url() -> str:
    """Get the database URL."""
    return get_secret("DATABASE_URL", "database-url")


def get_pgvector_db_url() -> str:
    """Get the PgVector database URL."""
    return get_secret("PGVECTOR_DB_URL", "pgvector-db-url")


def get_microsoft_client_secret() -> str:
    """Get the Microsoft OAuth client secret."""
    return get_secret("MICROSOFT_CLIENT_SECRET", "microsoft-client-secret")


def get_microsoft_client_id() -> str:
    """Get the Microsoft OAuth client ID."""
    return get_secret("MICROSOFT_CLIENT_ID", "microsoft-client-id")


def get_microsoft_tenant_id() -> str:
    """Get the Microsoft OAuth tenant ID."""
    return get_secret("MICROSOFT_CLIENT_TENANT_ID", "microsoft-tenant-id")


def get_gcs_bucket_name() -> str:
    """Get the GCS bucket name."""
    return get_secret("GCS_BUCKET_NAME", "gcs-bucket-name")


def get_google_application_credentials() -> str:
    """Get the Google application credentials path."""
    return get_secret("GOOGLE_APPLICATION_CREDENTIALS", "google-application-credentials")
