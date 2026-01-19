# backend/config.py
# Environment-aware configuration for Brinkadata backend

import os
from typing import Literal

# Environment detection
ENV: Literal["dev", "staging", "prod"] = os.environ.get("ENV", "dev")  # type: ignore
IS_DEV = (ENV == "dev")
IS_STAGING = (ENV == "staging")
IS_PROD = (ENV == "prod")

# JWT and session configuration
SECRET_KEY = os.environ.get("SECRET_KEY", "your-secret-key-here")  # TODO: Use secure key in prod
ALGORITHM = "HS256"

# Token lifetimes
ACCESS_TOKEN_MINUTES = int(os.environ.get("ACCESS_TOKEN_MINUTES", "15"))
REFRESH_TOKEN_DAYS = int(os.environ.get("REFRESH_TOKEN_DAYS", "7"))
RESUME_CODE_MINUTES = int(os.environ.get("RESUME_CODE_MINUTES", "10"))

# Database
DATABASE_PATH = os.environ.get("DATABASE_PATH", "brinkadata.db")

# CORS origins (expand for staging/prod)
CORS_ORIGINS = [
    "http://localhost:8501",  # Streamlit default
    "http://127.0.0.1:8501",
]

if IS_STAGING:
    # Add staging frontend URL
    CORS_ORIGINS.append(os.environ.get("STAGING_FRONTEND_URL", "https://staging.brinkadata.com"))

if IS_PROD:
    # Add production frontend URL
    CORS_ORIGINS.append(os.environ.get("PROD_FRONTEND_URL", "https://app.brinkadata.com"))

print(f"[CONFIG] Environment: {ENV}")
print(f"[CONFIG] Access token: {ACCESS_TOKEN_MINUTES} minutes")
print(f"[CONFIG] Refresh token: {REFRESH_TOKEN_DAYS} days")
print(f"[CONFIG] Resume code: {RESUME_CODE_MINUTES} minutes")
