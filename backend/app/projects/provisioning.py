"""Declare projects in a YAML file (``PROJECTS_FILE``) instead of creating them in the UI.

The file is applied on every start: listed projects are created or brought in
line with the file and marked *managed*, so their connection settings are
read-only in the UI and API. Dashboards, chats and notes are never touched.
A project removed from the file is not deleted, only un-managed.

Secrets are referenced as ``${ENV_VAR}`` so the file itself can live in git
or a ConfigMap.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Self

import yaml
from pydantic import Field, ValidationError, field_validator, model_validator

from app.models import CamelModel
from app.projects.models import Slug, Source, _clean_url, check_source_fields

_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ProvisioningError(ValueError):
    """The projects file cannot be read or is invalid; startup stops with this message."""


class ProvisionedProject(CamelModel):
    slug: Slug
    name: str | None = Field(default=None, min_length=1, max_length=80)
    source: Source = "prometheus"
    prometheus_url: str | None = None
    grafana_url: str | None = None
    grafana_datasource_uid: str | None = None
    username: str | None = None
    password: str | None = None
    tls_verify: bool | None = None

    _url = field_validator("prometheus_url", "grafana_url")(_clean_url)

    @field_validator("username", "password", "grafana_datasource_uid")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @model_validator(mode="after")
    def _source_fields(self) -> Self:
        check_source_fields(
            self.source, self.prometheus_url, self.grafana_url, self.grafana_datasource_uid
        )
        return self


class ProjectsFile(CamelModel):
    projects: list[ProvisionedProject] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_slugs(self) -> Self:
        seen: set[str] = set()
        for project in self.projects:
            if project.slug in seen:
                raise ValueError(f"slug {project.slug!r} appears more than once")
            seen.add(project.slug)
        return self


def expand_env(value: object, env: Mapping[str, str], where: str = "") -> object:
    """Replace ``${VAR}`` in every string; an unset variable is an error, not an empty string."""
    if isinstance(value, str):

        def substitute(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in env:
                raise ProvisioningError(
                    f"{where or 'value'} references ${{{name}}}, which is unset"
                )
            return env[name]

        return _ENV_REF.sub(substitute, value)
    if isinstance(value, list):
        return [expand_env(v, env, f"{where}[{i}]") for i, v in enumerate(value)]
    if isinstance(value, dict):
        return {
            k: expand_env(v, env, f"{where}.{k}" if where else str(k)) for k, v in value.items()
        }
    return value


def load_projects_file(path: Path, env: Mapping[str, str] | None = None) -> ProjectsFile:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProvisioningError(f"cannot read PROJECTS_FILE {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ProvisioningError(f"PROJECTS_FILE {path} is not valid YAML: {exc}") from exc
    if raw is None:
        return ProjectsFile()
    if not isinstance(raw, dict):
        raise ProvisioningError(f"PROJECTS_FILE {path}: expected a mapping with a 'projects' list")
    expanded = expand_env(raw, os.environ if env is None else env)
    try:
        return ProjectsFile.model_validate(expanded)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'file'}: {err['msg']}"
            for err in exc.errors()
        )
        raise ProvisioningError(f"PROJECTS_FILE {path} is invalid: {problems}") from exc
