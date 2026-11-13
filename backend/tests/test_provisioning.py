"""Projects declared in PROJECTS_FILE."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.projects.provisioning import ProvisioningError, expand_env, load_projects_file

FILE = """
projects:
  - slug: prod-eu
    name: Production EU
    source: grafana
    grafanaUrl: https://grafana.example.com/
    grafanaDatasourceUid: mimir-eu
    username: prompilot
    password: ${PP_TEST_GRAFANA_PASSWORD}
  - slug: staging
    prometheusUrl: http://prometheus.staging:9090
    tlsVerify: false
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "projects.yaml"
    path.write_text(text, encoding="utf-8")
    return path


# ---- file parsing ---------------------------------------------------------------


def test_load_file_expands_env(tmp_path: Path) -> None:
    parsed = load_projects_file(_write(tmp_path, FILE), {"PP_TEST_GRAFANA_PASSWORD": "s3cret"})
    prod, staging = parsed.projects
    assert prod.grafana_url == "https://grafana.example.com"
    assert prod.password == "s3cret"
    assert staging.source == "prometheus" and staging.tls_verify is False
    assert staging.name is None


def test_empty_file_means_no_projects(tmp_path: Path) -> None:
    assert load_projects_file(_write(tmp_path, ""), {}).projects == []


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (FILE, "projects[0].password references ${PP_TEST_GRAFANA_PASSWORD}, which is unset"),
        ("projects:\n  - slug: a\n", "prometheusUrl is required"),
        (
            "projects:\n  - {slug: a, prometheusUrl: 'http://a'}\n"
            "  - {slug: a, prometheusUrl: 'http://b'}\n",
            "slug 'a' appears more than once",
        ),
        ("projects:\n  - {slug: a, prometheusUrl: 'http://a', pasword: x}\n", "pasword"),
        ("projects:\n  - {slug: 'Not A Slug', prometheusUrl: 'http://a'}\n", "slug"),
        ("projects: [\n", "not valid YAML"),
        ("- a\n- b\n", "expected a mapping"),
    ],
)
def test_invalid_files_are_explained(tmp_path: Path, text: str, message: str) -> None:
    with pytest.raises(ProvisioningError) as info:
        load_projects_file(_write(tmp_path, text), {})
    assert message in str(info.value)


def test_validation_errors_do_not_echo_secrets(tmp_path: Path) -> None:
    text = "projects:\n  - {slug: a, source: grafana, password: hunter2-secret}\n"
    with pytest.raises(ProvisioningError) as info:
        load_projects_file(_write(tmp_path, text), {})
    assert "hunter2-secret" not in str(info.value)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ProvisioningError, match="cannot read PROJECTS_FILE"):
        load_projects_file(tmp_path / "nope.yaml", {})


def test_expand_env_leaves_plain_dollars_alone() -> None:
    assert expand_env({"a": ["p$ss", "${X}-$Y"]}, {"X": "1"}) == {"a": ["p$ss", "1-$Y"]}


# ---- applied on startup ---------------------------------------------------------


@pytest.fixture
def start_app(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[Callable[[str | None], TestClient]]:
    """Start the app (again) on the same DATA_DIR with a given projects file."""
    monkeypatch.setenv("PROMETHEUS_URL", "http://prom.test:9090")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CATALOG_AUTOSTART", "false")
    monkeypatch.setenv("PP_TEST_GRAFANA_PASSWORD", "s3cret")
    clients: list[TestClient] = []

    def start(text: str | None) -> TestClient:
        for running in clients:
            running.__exit__(None, None, None)
        clients.clear()
        if text is None:
            monkeypatch.delenv("PROJECTS_FILE", raising=False)
        else:
            monkeypatch.setenv("PROJECTS_FILE", str(_write(tmp_path, text)))
        get_settings.cache_clear()
        client = TestClient(create_app())
        client.__enter__()
        clients.append(client)
        return client

    try:
        yield start
    finally:
        for running in clients:
            running.__exit__(None, None, None)
        get_settings.cache_clear()


def test_file_creates_managed_projects(start_app: Callable[[str | None], TestClient]) -> None:
    client = start_app(FILE)
    projects = {p["slug"]: p for p in client.get("/api/projects").json()}
    # The file replaces the env-derived default project on a fresh install.
    assert set(projects) == {"prod-eu", "staging"}
    prod = projects["prod-eu"]
    assert prod["managed"] is True
    assert prod["source"] == "grafana"
    assert prod["grafanaDatasourceUid"] == "mimir-eu"
    assert prod["prometheusUsername"] == "prompilot"
    assert prod["hasPassword"] is True
    assert projects["staging"]["name"] == "staging"  # slug when no name is given
    assert projects["staging"]["tlsVerify"] is False

    runtime = client.app.state.projects._runtimes["prod-eu"]  # type: ignore[attr-defined]
    assert runtime.prometheus.via_grafana
    assert runtime.prometheus._http.auth._auth_header.startswith("Basic ")


def test_managed_projects_are_read_only(start_app: Callable[[str | None], TestClient]) -> None:
    client = start_app(FILE)
    patched = client.patch("/api/projects/staging", json={"name": "Renamed"})
    assert patched.status_code == 409
    assert "managed by the projects file" in patched.json()["detail"]
    assert client.delete("/api/projects/staging").status_code == 409
    # Dashboards inside a managed project stay fully editable.
    assert client.post("/api/projects/staging/dashboards", json={"title": "Ops"}).status_code in (
        200,
        201,
    )


def test_restart_applies_changes_and_keeps_data(
    start_app: Callable[[str | None], TestClient],
) -> None:
    client = start_app(FILE)
    client.post("/api/projects/staging/dashboards", json={"title": "Ops"})
    before = {d["title"] for d in client.get("/api/projects/staging/dashboards").json()}

    client = start_app(
        FILE.replace("http://prometheus.staging:9090", "http://prometheus.staging:9091")
    )
    staging = client.get("/api/projects/staging").json()
    assert staging["prometheusUrl"] == "http://prometheus.staging:9091"
    after = {d["title"] for d in client.get("/api/projects/staging/dashboards").json()}
    assert after == before and "Ops" in after


def test_removed_from_file_becomes_editable(start_app: Callable[[str | None], TestClient]) -> None:
    start_app(FILE)
    only_prod = FILE.split("  - slug: staging")[0]
    client = start_app(only_prod)
    staging = client.get("/api/projects/staging").json()
    assert staging["managed"] is False  # kept, not deleted
    assert client.patch("/api/projects/staging", json={"name": "Mine"}).status_code == 200
    assert client.get("/api/projects/prod-eu").json()["managed"] is True

    client = start_app(None)  # PROJECTS_FILE unset: nothing stays locked
    assert all(not p["managed"] for p in client.get("/api/projects").json())


def test_file_takes_over_an_existing_project(
    start_app: Callable[[str | None], TestClient],
) -> None:
    client = start_app(None)
    client.post(
        "/api/projects/default/dashboards/overview/panels",
        json={
            "spec": {
                "type": "stat",
                "title": "Up",
                "queries": [{"refId": "A", "expr": "up"}],
                "unit": "none",
            }
        },
    )
    client = start_app(
        "projects:\n  - slug: default\n    name: Main\n    prometheusUrl: http://new:9090\n"
    )
    default = client.get("/api/projects/default").json()
    assert default["managed"] is True
    assert default["name"] == "Main"
    assert default["prometheusUrl"] == "http://new:9090"
    assert len(client.get("/api/projects/default/dashboards/overview").json()["panels"]) == 1


def test_invalid_file_stops_startup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CATALOG_AUTOSTART", "false")
    monkeypatch.setenv("PROJECTS_FILE", str(_write(tmp_path, "projects:\n  - slug: a\n")))
    get_settings.cache_clear()
    try:
        with (
            pytest.raises(ProvisioningError, match="prometheusUrl is required"),
            TestClient(create_app()),
        ):
            pass
    finally:
        get_settings.cache_clear()
