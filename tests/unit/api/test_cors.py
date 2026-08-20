from __future__ import annotations

from fastapi.testclient import TestClient

from route_agent_api.app import create_app
from route_agent_api.bind import listen_host, listen_port
from route_agent_api.cors import cors_origin_regex, cors_origins


class TestCors:
    def test_local_vite_origin_is_allowed(self) -> None:
        client = TestClient(create_app())
        response = client.get(
            "/api/health",
            headers={"Origin": "http://127.0.0.1:5173"},
        )
        assert response.status_code == 200
        assert (
            response.headers.get("access-control-allow-origin")
            == "http://127.0.0.1:5173"
        )

    def test_vercel_preview_origin_is_allowed(self) -> None:
        client = TestClient(create_app())
        origin = "https://trace-viewer-git-main-team.vercel.app"
        response = client.get("/api/health", headers={"Origin": origin})
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == origin

    def test_unknown_origin_is_rejected(self) -> None:
        client = TestClient(create_app())
        response = client.get(
            "/api/health",
            headers={"Origin": "https://evil.example"},
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") is None

    def test_extra_origins_come_from_env(self, monkeypatch: object) -> None:
        monkeypatch.setenv(  # type: ignore[attr-defined]
            "ROUTE_AGENT_CORS_ORIGINS",
            "https://explorer.example.com, https://other.example.com",
        )
        assert "https://explorer.example.com" in cors_origins()
        assert "https://other.example.com" in cors_origins()

    def test_regex_can_be_disabled(self, monkeypatch: object) -> None:
        monkeypatch.setenv("ROUTE_AGENT_CORS_ORIGIN_REGEX", "")  # type: ignore[attr-defined]
        assert cors_origin_regex() is None


class TestBind:
    def test_defaults_to_loopback_8000(self, monkeypatch: object) -> None:
        monkeypatch.delenv("ROUTE_AGENT_API_HOST", raising=False)  # type: ignore[attr-defined]
        monkeypatch.delenv("ROUTE_AGENT_API_PORT", raising=False)  # type: ignore[attr-defined]
        monkeypatch.delenv("PORT", raising=False)  # type: ignore[attr-defined]
        assert listen_host() == "127.0.0.1"
        assert listen_port() == 8000

    def test_railway_port_wins(self, monkeypatch: object) -> None:
        monkeypatch.setenv("PORT", "8080")  # type: ignore[attr-defined]
        monkeypatch.setenv("ROUTE_AGENT_API_PORT", "8000")  # type: ignore[attr-defined]
        monkeypatch.setenv("ROUTE_AGENT_API_HOST", "0.0.0.0")  # type: ignore[attr-defined]
        assert listen_host() == "0.0.0.0"
        assert listen_port() == 8080
