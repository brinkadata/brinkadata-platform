# frontend/config.py
# Environment-aware configuration for Brinkadata frontend

import os
from typing import Literal

# Environment detection - normalize to lowercase
_raw_env = os.environ.get("ENV", "production").lower()
ENV: Literal["local", "staging", "production"] = _raw_env if _raw_env in ("local", "staging", "production") else "production"  # type: ignore

# Environment flags (using normalized ENV)
IS_LOCAL = (ENV == "local")
IS_STAGING = (ENV == "staging")
IS_PROD = (ENV == "production")

# Legacy aliases (backward compatibility)
IS_DEV = IS_LOCAL


def get_env() -> Literal["local", "staging", "production"]:
    """
    Get current environment with normalization.
    
    Returns:
        "local", "staging", or "production" (default on Render)
    """
    return ENV


def validate_api_url(url: str, env: str) -> None:
    """
    Validate API base URL according to environment security rules.
    
    Args:
        url: The API base URL to validate
        env: Current environment ("local", "staging", "production")
    
    Raises:
        ValueError: If URL violates security constraints for the environment
    """
    if not url:
        raise ValueError("API base URL cannot be empty")
    
    # Production/staging must use HTTPS and never localhost
    if env in ("staging", "production"):
        if not url.startswith("https://"):
            raise ValueError(f"Production/staging must use HTTPS. Got: {url}")
        if "127.0.0.1" in url or "localhost" in url:
            raise ValueError(f"Production/staging cannot use localhost URLs. Got: {url}")


def get_api_base_url() -> str:
    """
    Get API base URL with strict priority and validation.
    
    Priority:
    1. BACKEND_URL environment variable
    2. API_BASE_URL environment variable  
    3. Local dev default (http://127.0.0.1:8000) ONLY if ENV == "local"
    4. Raise error if production/staging with no configured URL
    
    Returns:
        Validated API base URL with trailing slash removed
    
    Raises:
        RuntimeError: If production/staging environment has no configured URL
    """
    # Priority 1: BACKEND_URL (primary)
    backend_url = os.environ.get("BACKEND_URL", "").strip()
    if backend_url:
        url = backend_url.rstrip("/")
        validate_api_url(url, ENV)
        return url
    
    # Priority 2: API_BASE_URL (legacy support)
    api_base_url = os.environ.get("API_BASE_URL", "").strip()
    if api_base_url:
        url = api_base_url.rstrip("/")
        validate_api_url(url, ENV)
        return url
    
    # Priority 3: Local dev default ONLY
    if ENV == "local":
        return "http://127.0.0.1:8000"
    
    # Priority 4: Error for production/staging without config
    raise RuntimeError(
        f"🚨 Backend URL not configured for {ENV.upper()} environment. "
        f"Set BACKEND_URL environment variable on Render with your backend service URL. "
        f"Production/staging MUST use HTTPS and cannot fall back to localhost."
    )


# Initialize BACKEND_URL for backwards compatibility
try:
    BACKEND_URL = get_api_base_url()
except RuntimeError as e:
    # In production, this should never happen - fail fast
    print(f"[CONFIG] CRITICAL: {e}")
    BACKEND_URL = ""  # Will cause errors on API calls, which is correct behavior

# Token lifetimes (for display only; backend enforces)
ACCESS_TOKEN_MINUTES = int(os.environ.get("ACCESS_TOKEN_MINUTES", "15"))
REFRESH_TOKEN_DAYS = int(os.environ.get("REFRESH_TOKEN_DAYS", "7"))
RESUME_CODE_MINUTES = int(os.environ.get("RESUME_CODE_MINUTES", "10"))

# Feature flags
ENABLE_DEBUG_UI = IS_DEV  # Show debug buttons/info only in dev
ENABLE_VERBOSE_LOGGING = IS_DEV or IS_STAGING

print(f"[CONFIG] Environment: {ENV}")
print(f"[CONFIG] Backend URL: {BACKEND_URL}")
print(f"[CONFIG] Debug UI: {'enabled' if ENABLE_DEBUG_UI else 'disabled'}")
