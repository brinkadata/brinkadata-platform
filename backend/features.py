"""
Feature gating + plan/usage helpers for Brinkadata.

This module is intentionally dependency-light and uses sqlite3 directly so the
FastAPI app can call it without circular imports.

TASK 5: All plan enforcement is server-side (never trust frontend).
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from typing import Dict, Optional


# Keep DB path consistent with backend/main.py
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
DB_PATH = os.getenv("BRINKADATA_DB", os.path.join(PROJECT_ROOT, "backend", "brinkadata.db"))


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---- Plan + feature map -------------------------------------------------


@dataclass(frozen=True)
class Plan:
    """
    TASK 5: Server-side plan definition (source of truth for limits/features).
    Frontend must never implement plan logic independently.
    """
    name: str
    saved_deals_limit: int
    scenarios_limit: int
    exports_enabled: bool
    irr_npv_enabled: bool
    api_access_enabled: bool


PLANS: Dict[str, Plan] = {
    "free": Plan("free", saved_deals_limit=25, scenarios_limit=3, exports_enabled=False, irr_npv_enabled=False, api_access_enabled=False),
    "pro": Plan("pro", saved_deals_limit=250, scenarios_limit=25, exports_enabled=True, irr_npv_enabled=True, api_access_enabled=False),
    "team": Plan("team", saved_deals_limit=1000, scenarios_limit=100, exports_enabled=True, irr_npv_enabled=True, api_access_enabled=True),
    "enterprise": Plan("enterprise", saved_deals_limit=10_000, scenarios_limit=500, exports_enabled=True, irr_npv_enabled=True, api_access_enabled=True),
}


def get_plan_features(account_id: int) -> Dict[str, any]:
    """
    TASK 5: Get plan capabilities for an account (server-side source of truth).
    Returns dict with limits and feature flags.
    """
    plan_name = get_account_plan(account_id)
    plan = PLANS.get(plan_name, PLANS["free"])
    
    return {
        "max_saved_deals": plan.saved_deals_limit,
        "max_scenarios": plan.scenarios_limit,
        "can_export": plan.exports_enabled,
        "can_use_irr_npv": plan.irr_npv_enabled,
        "can_use_api": plan.api_access_enabled,
    }


def get_account_plan(account_id: int) -> str:
    """
    Return the active plan name for an account.

    Uses the subscriptions table if present; otherwise falls back to 'free'.
    """
    try:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(s.plan_name, a.plan_name, 'free') AS plan_name
                FROM accounts a
                LEFT JOIN subscriptions s
                  ON s.account_id = a.id
                 AND (s.status IS NULL OR s.status IN ('active','trialing'))
                WHERE a.id = ?
                ORDER BY COALESCE(s.created_at, '') DESC
                LIMIT 1
                """,
                (account_id,),
            ).fetchone()
            if row and row["plan_name"]:
                return str(row["plan_name"]).lower()
    except Exception:
        pass
    return "free"


def get_limit(account_id: int, limit_name: str) -> int:
    plan_name = get_account_plan(account_id)
    plan = PLANS.get(plan_name, PLANS["free"])

    if limit_name == "saved_deals":
        return plan.saved_deals_limit
    if limit_name == "scenarios":
        return plan.scenarios_limit

    # Unknown limit -> treat as "effectively unlimited" for safety
    return 1_000_000


def check_feature_access(account_id: int, feature_name: str) -> bool:
    plan_name = get_account_plan(account_id)
    plan = PLANS.get(plan_name, PLANS["free"])
    feature_name = feature_name.lower()

    if feature_name in ("exports", "csv_export"):
        return plan.exports_enabled
    if feature_name in ("irr", "npv", "irr_npv"):
        return plan.irr_npv_enabled
    if feature_name in ("api", "api_access"):
        return plan.api_access_enabled

    # default: allow
    return True


# ---- Usage stats --------------------------------------------------------


def get_usage_stats(account_id: int) -> Dict[str, int]:
    """Return current usage counts used by gating/limits."""
    stats = {"saved_deals": 0, "scenarios": 0}
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM saved_properties WHERE account_id = ?",
                (account_id,),
            ).fetchone()
            if row:
                stats["saved_deals"] = int(row["n"])

            # scenarios table is optional (some builds store scenarios in json)
            try:
                row2 = conn.execute(
                    "SELECT COUNT(*) AS n FROM scenarios WHERE account_id = ?",
                    (account_id,),
                ).fetchone()
                if row2:
                    stats["scenarios"] = int(row2["n"])
            except Exception:
                stats["scenarios"] = 0
    except Exception:
        pass
    return stats


# ---- Limit checking -----------------------------------------------------


class UsageLimitError(Exception):
    """TASK 5: Raised when an account exceeds plan limits."""
    pass


class FeatureNotAllowedError(Exception):
    """TASK 5: Raised when an account tries to use a feature not in their plan."""
    pass


def require_feature(account_id: int, feature_name: str) -> None:
    """
    TASK 5: Enforce feature access (raises FeatureNotAllowedError if not allowed).
    Use this decorator/helper pattern in endpoints that require plan features.
    
    Example:
        require_feature(account_id, "can_use_irr_npv")
        require_feature(account_id, "can_export")
    """
    features = get_plan_features(account_id)
    
    if feature_name not in features or not features[feature_name]:
        plan_name = get_account_plan(account_id)
        raise FeatureNotAllowedError(f"Feature '{feature_name}' not available on {plan_name} plan")


def require_limit(account_id: int, limit_name: str, current_count: int) -> None:
    """
    TASK 5: Enforce usage limits (raises UsageLimitError if at/over limit).
    Use before operations that increment usage.
    
    Example:
        require_limit(account_id, "max_saved_deals", current_saved_count)
    """
    features = get_plan_features(account_id)
    limit_key = f"max_{limit_name}"
    
    if limit_key not in features:
        # Unknown limit, allow (fail-open for unknown limits)
        return
    
    limit = features[limit_key]
    if current_count >= limit:
        plan_name = get_account_plan(account_id)
        raise UsageLimitError(f"Limit reached for {limit_name}: {current_count}/{limit} ({plan_name} plan)")


def check_usage_limit(account_id: int, limit_name: str, current_usage: Optional[int] = None) -> None:
    """
    TASK 5: Legacy wrapper for require_limit (maintains backward compatibility).
    Raise UsageLimitError if the account is at/over its plan limit.

    This signature intentionally matches how backend/main.py calls it:
        check_usage_limit(account_id, "saved_deals")
    """
    if current_usage is None:
        current_usage = get_usage_stats(account_id).get(limit_name, 0)

    limit = get_limit(account_id, limit_name)
    if current_usage >= limit:
        raise UsageLimitError(f"Limit reached for {limit_name}: {current_usage}/{limit}")
