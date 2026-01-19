from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum

# Enums
class UserRole(str, Enum):
    owner = "owner"
    admin = "admin"
    member = "member"
    read_only = "read_only"
    affiliate = "affiliate"

class PlanName(str, Enum):
    free = "free"
    pro = "pro"
    team = "team"
    enterprise = "enterprise"

# Models
class User(BaseModel):
    id: Optional[int] = None
    email: str
    password_hash: str
    account_id: int
    role: UserRole = UserRole.member
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True

class Account(BaseModel):
    id: Optional[int] = None
    name: str
    plan: PlanName = PlanName.free
    created_at: datetime = Field(default_factory=datetime.utcnow)
    stripe_customer_id: Optional[str] = None

class Plan(BaseModel):
    id: Optional[int] = None
    name: PlanName
    stripe_id: Optional[str] = None
    features: Dict[str, Any] = Field(default_factory=dict)  # e.g., {"can_export_csv": True, "max_saved_deals": 20}
    limits: Dict[str, Any] = Field(default_factory=dict)
    price_monthly: float = 0.0

class Subscription(BaseModel):
    id: Optional[int] = None
    account_id: int
    plan_id: int
    status: str = "active"  # active, canceled, past_due
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool = False

class Affiliate(BaseModel):
    id: Optional[int] = None
    user_id: int
    referral_code: str
    commission_rate: float = 0.1  # 10%
    total_earned: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Referral(BaseModel):
    id: Optional[int] = None
    affiliate_id: int
    referred_user_id: int
    event: str  # signup, upgrade
    amount: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Scenario(BaseModel):
    id: Optional[int] = None
    account_id: int
    property_id: int
    slot: str  # "A", "B", "C"
    label: Optional[str] = None
    metrics_json: str  # JSON-serialized analysis output
    created_at: datetime = Field(default_factory=datetime.utcnow)