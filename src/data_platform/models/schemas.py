"""Pydantic v2 models for the source API payload.

This is the "validate data as it comes in" layer at the edge of the system:
every record from the API is parsed/validated here before it is allowed any
further. Invalid records raise immediately rather than silently corrupting bronze.

(Plain dataclasses are still part of stdlib, but they do no validation or
coercion — Pydantic v2 is the current best-in-class choice for this boundary.)
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Geo(BaseModel):
    lat: float
    lng: float


class Address(BaseModel):
    street: str
    suite: str = ""
    city: str
    zipcode: str
    geo: Geo


class Company(BaseModel):
    name: str


class User(BaseModel):
    """One user record as returned by the source API."""

    id: int = Field(ge=1)
    name: str
    username: str
    email: str  # source data is not RFC-strict; keep as str, dbt asserts shape
    phone: str = ""
    website: str = ""
    address: Address
    company: Company

    def to_flat(self) -> dict:
        """Flatten the nested record into a single bronze row."""
        return {
            "id": self.id,
            "name": self.name,
            "username": self.username,
            "email": self.email,
            "phone": self.phone,
            "website": self.website,
            "company_name": self.company.name,
            "city": self.address.city,
            "zipcode": self.address.zipcode,
            "lat": self.address.geo.lat,
            "lng": self.address.geo.lng,
        }


__all__ = ["User", "Address", "Company", "Geo"]
