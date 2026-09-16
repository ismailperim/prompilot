# Adding a panel type

> Draft — the registry lands in milestone M2. This page will be completed then.

Panels are self-contained modules. Adding one never requires changing core
code. A panel type consists of:

1. **Backend module** `backend/app/panels/<type>.py` — a `PanelModule` with
   the type name, an options schema (Pydantic), a `to_grafana()` mapper and a
   short description that tells the LLM when to pick this panel.
2. **Registration** — one `register()` call.
3. **Frontend component** `frontend/src/panels/<Type>.tsx` — renders
   `({ spec, frames, timeRange })`, plus one entry in the frontend registry.
4. **Tests** — options round-trip and a Grafana JSON golden snapshot.
