# frontend/config.py
# Environment-aware configuration for Brinkadata frontend

import os
from typing import Literal

# Environment detection
ENV: Literal["dev", "staging", "prod"] = os.environ.get("ENV", "dev")  # type: ignore
IS_DEV = (ENV == "dev")
IS_STAGING = (ENV == "staging")
IS_PROD = (ENV == "prod")

# Backend API URL
if IS_PROD:
    BACKEND_URL = os.environ.get("BACKEND_URL", "https://api.brinkadata.com")
elif IS_STAGING:
    BACKEND_URL = os.environ.get("BACKEND_URL", "https://api-staging.brinkadata.com")
else:  # dev
    BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")

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
