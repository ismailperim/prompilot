"""Shared Pydantic base classes."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Model that speaks camelCase on the wire and snake_case in Python.

    ``extra="forbid"`` is deliberate: specs may come from an LLM, and a
    hallucinated field should fail validation instead of being ignored.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
        extra="forbid",
    )
