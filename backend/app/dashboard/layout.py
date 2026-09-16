"""Grid placement helpers."""

from __future__ import annotations

from app.dashboard.models import GRID_COLUMNS, Layout, PanelPlacement


def find_free_slot(panels: list[PanelPlacement], w: int, h: int) -> Layout:
    """First-fit placement: scan rows top-down, columns left-right, return the first gap."""
    w = min(w, GRID_COLUMNS)
    occupied: set[tuple[int, int]] = set()
    for placement in panels:
        lay = placement.layout
        occupied.update(
            (x, y) for x in range(lay.x, lay.x + lay.w) for y in range(lay.y, lay.y + lay.h)
        )

    bottom = max((p.layout.y + p.layout.h for p in panels), default=0)
    for y in range(bottom + 1):
        for x in range(GRID_COLUMNS - w + 1):
            cells = ((cx, cy) for cx in range(x, x + w) for cy in range(y, y + h))
            if not any(cell in occupied for cell in cells):
                return Layout(x=x, y=y, w=w, h=h)
    return Layout(x=0, y=bottom, w=w, h=h)
