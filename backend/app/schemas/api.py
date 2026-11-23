from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator



class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)


class RequestFields(BaseModel):
    item: str | None = Field(default=None, max_length=300)
    category: str | None = Field(default=None, max_length=60)
    quantity: int | None = Field(default=None, ge=1, le=1000)
    purpose: str | None = Field(default=None, max_length=300)
    required_date: date | None = None
    required_date_text: str | None = Field(default=None, max_length=100)
    budget: int | None = Field(default=None, ge=0, le=1_000_000_000)
    requirements: str | None = Field(default=None, max_length=2000)
    requester_name: str | None = Field(default=None, max_length=200)


class RequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["web_form", "text", "email", "api"] = "text"
    text: str | None = Field(default=None, max_length=8000)
    fields: RequestFields | None = None

    @model_validator(mode="after")
    def _need_input(self):
        has_text = bool(self.text and self.text.strip())
        has_fields = bool(self.fields and any(v not in (None, "") for v in self.fields.model_dump().values()))
        if not has_text and not has_fields:
            raise ValueError("Provide either free text or at least one structured field.")
        return self


class RequestUpdate(RequestFields):
    pass


class DecisionIn(BaseModel):
    action: Literal["approve", "reject", "modify", "escalate"]
    note: str | None = Field(default=None, max_length=2000)
    modification: dict | None = None

    @field_validator("modification")
    @classmethod
    def _mod(cls, v):
        if not v:  # None / {} - only a 'modify' action needs content, and the service refuses it there
            return v
        if set(v) - {"vendor_id"}:
            raise ValueError("Only 'vendor_id' can be modified.")
        vendor_id = v.get("vendor_id")
        if isinstance(vendor_id, bool) or not isinstance(vendor_id, int) or vendor_id < 1:
            raise ValueError("'vendor_id' must be a positive integer.")
        return v


class PolicyUpdate(BaseModel):
    params: dict | None = None
    enabled: bool | None = None
    severity: Literal["block", "warn"] | None = None


class PolicyChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy_id: int
    params: dict | None = None
    enabled: bool | None = None
    severity: Literal["block", "warn"] | None = None


class WhatIfPurchase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: int = Field(..., ge=0, le=100_000_000)
    category: str = Field(..., min_length=1, max_length=50)
    quantity: int = Field(1, ge=1, le=1000)
    budget: int | None = Field(None, ge=0, le=100_000_000)
    vendor_approved: bool = True
    price_delta_pct: float | None = Field(None, ge=-100, le=1000)
    vendors_compared: int = Field(3, ge=0, le=50)
    item: str | None = Field(None, max_length=200)
    purpose: str | None = Field(None, max_length=500)


class SimulateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    changes: list[PolicyChange] = Field(default_factory=list, max_length=20)
    sample: int = Field(500, ge=1, le=1000)
    purchase: WhatIfPurchase | None = None


class VendorUpdate(BaseModel):
    approved: bool | None = None
    available: bool | None = None


class IntegrationUpdate(BaseModel):
    status: Literal["connected", "disconnected"]


class DemoIn(BaseModel):
    scenario: Literal["laptop_primary", "vendor_outage", "routine", "high_value", "blocked_category"] = "laptop_primary"
