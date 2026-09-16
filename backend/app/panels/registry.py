"""Registry of panel modules: the only place the core learns about panel types."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.panels.base import PanelModule, PanelSpec


class PanelValidationError(ValueError):
    """A spec failed validation. ``errors`` are short, LLM-readable messages."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


class UnknownPanelTypeError(PanelValidationError):
    def __init__(self, panel_type: str, known: list[str]) -> None:
        super().__init__([f"type: unknown panel type {panel_type!r}; expected one of {known}"])
        self.panel_type = panel_type


def _format_errors(exc: ValidationError, prefix: str = "") -> list[str]:
    messages = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"])
        path = f"{prefix}{loc}" if loc else prefix.rstrip(".") or "spec"
        messages.append(f"{path}: {err['msg']}")
    return messages


class PanelRegistry:
    def __init__(self) -> None:
        self._modules: dict[str, PanelModule] = {}

    def register(self, module: PanelModule) -> None:
        if module.type in self._modules:
            raise ValueError(f"panel type {module.type!r} is already registered")
        self._modules[module.type] = module

    def get(self, panel_type: str) -> PanelModule:
        try:
            return self._modules[panel_type]
        except KeyError:
            raise UnknownPanelTypeError(panel_type, self.types()) from None

    def types(self) -> list[str]:
        return sorted(self._modules)

    def modules(self) -> list[PanelModule]:
        return [self._modules[t] for t in self.types()]

    def validate(self, data: dict[str, Any] | PanelSpec) -> PanelSpec:
        """Validate a raw spec, including ``options`` against its type's model.

        Returns a spec whose ``options`` are normalised (defaults filled in),
        so downstream code can rely on every option being present.
        """
        try:
            spec = data if isinstance(data, PanelSpec) else PanelSpec.model_validate(data)
        except ValidationError as exc:
            raise PanelValidationError(_format_errors(exc)) from exc

        module = self.get(spec.type)
        try:
            options = module.options_model.model_validate(spec.options)
        except ValidationError as exc:
            raise PanelValidationError(_format_errors(exc, prefix="options.")) from exc

        return spec.model_copy(update={"options": options.model_dump(by_alias=True)})

    def to_grafana(self, spec: PanelSpec) -> dict[str, Any]:
        return self.get(spec.type).to_grafana(spec)


registry = PanelRegistry()
