"""Panel types. Adding one: create a module exposing ``MODULE`` and register it here."""

from app.panels import timeseries
from app.panels.base import PanelModule, PanelSpec, Query, Unit
from app.panels.registry import PanelValidationError, UnknownPanelTypeError, registry

registry.register(timeseries.MODULE)

__all__ = [
    "PanelModule",
    "PanelSpec",
    "PanelValidationError",
    "Query",
    "Unit",
    "UnknownPanelTypeError",
    "registry",
]
