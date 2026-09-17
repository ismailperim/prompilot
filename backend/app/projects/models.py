from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated

from pydantic import Field, StringConstraints, field_validator

from app.models import CamelModel

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")]


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40].strip("-")
    return slug or "project"


class Project(CamelModel):
    slug: Slug
    name: str = Field(min_length=1, max_length=80)
    prometheus_url: str
    prometheus_username: str | None = None
    has_password: bool = False
    created_at: datetime
    updated_at: datetime


class ProjectCreate(CamelModel):
    name: str = Field(min_length=1, max_length=80)
    slug: Slug | None = Field(default=None, description="Derived from the name when omitted")
    prometheus_url: str = Field(min_length=1)
    prometheus_username: str | None = None
    prometheus_password: str | None = None

    @field_validator("prometheus_url")
    @classmethod
    def _url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not re.match(r"^https?://", value):
            raise ValueError("must start with http:// or https://")
        return value


class ProjectUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    prometheus_url: str | None = None
    prometheus_username: str | None = None
    prometheus_password: str | None = None
    clear_password: bool = False

    @field_validator("prometheus_url")
    @classmethod
    def _url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().rstrip("/")
        if not re.match(r"^https?://", value):
            raise ValueError("must start with http:// or https://")
        return value
