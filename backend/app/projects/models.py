from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from app.models import CamelModel

Source = Literal["prometheus", "grafana"]

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")]


def _clean_url(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip().rstrip("/")
    if not value:
        return None
    if not re.match(r"^https?://", value):
        raise ValueError("must start with http:// or https://")
    return value


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40].strip("-")
    return slug or "project"


class Project(CamelModel):
    slug: Slug
    name: str = Field(min_length=1, max_length=80)
    source: Source = "prometheus"
    # Empty when the project goes through Grafana.
    prometheus_url: str = ""
    grafana_url: str | None = None
    grafana_datasource_uid: str | None = None
    # Credentials for whichever server the project talks to (Prometheus or Grafana).
    prometheus_username: str | None = None
    has_password: bool = False
    tls_verify: bool = True
    created_at: datetime
    updated_at: datetime


class ProjectCreate(CamelModel):
    name: str = Field(min_length=1, max_length=80)
    slug: Slug | None = Field(default=None, description="Derived from the name when omitted")
    source: Source = Field(
        default="prometheus",
        description="prometheus = query Prometheus directly; grafana = through a Grafana "
        "datasource proxy (grafanaUrl + grafanaDatasourceUid)",
    )
    prometheus_url: str | None = None
    grafana_url: str | None = None
    grafana_datasource_uid: str | None = None
    prometheus_username: str | None = None
    prometheus_password: str | None = None
    tls_verify: bool | None = Field(
        default=None,
        description="Verify the server's TLS certificate (instance default when omitted)",
    )

    _url = field_validator("prometheus_url", "grafana_url")(_clean_url)

    @model_validator(mode="after")
    def _source_fields(self) -> Self:
        check_source_fields(
            self.source, self.prometheus_url, self.grafana_url, self.grafana_datasource_uid
        )
        return self


class ProjectUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    source: Source | None = None
    prometheus_url: str | None = None
    grafana_url: str | None = None
    grafana_datasource_uid: str | None = None
    prometheus_username: str | None = None
    prometheus_password: str | None = None
    clear_password: bool = False
    tls_verify: bool | None = None

    _url = field_validator("prometheus_url", "grafana_url")(_clean_url)


def check_source_fields(
    source: Source,
    prometheus_url: str | None,
    grafana_url: str | None,
    grafana_datasource_uid: str | None,
) -> None:
    """The fields the chosen source needs are present."""
    if source == "prometheus" and not prometheus_url:
        raise ValueError("prometheusUrl is required")
    if source == "grafana" and not (grafana_url and (grafana_datasource_uid or "").strip()):
        raise ValueError("grafanaUrl and grafanaDatasourceUid are required for a Grafana source")
