"""GET /config — server-driven client flags (W4 paywall activation)."""

from fastapi.testclient import TestClient


def _client():
    from main import app
    return TestClient(app)


class TestClientConfig:
    def test_subscription_flag_defaults_off(self):
        resp = _client().get("/config")
        assert resp.status_code == 200
        assert resp.json()["feature_subscription"] is False

    def test_subscription_flag_flips_via_env(self, monkeypatch):
        monkeypatch.setenv("FEATURE_SUBSCRIPTION", "true")
        from app.feature_flags import get_feature_flags
        get_feature_flags.cache_clear()
        try:
            resp = _client().get("/config")
            assert resp.json()["feature_subscription"] is True
        finally:
            get_feature_flags.cache_clear()
