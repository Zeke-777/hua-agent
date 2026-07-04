"""Smoke test for main.py entry point."""


class TestMain:
    def test_create_app(self):
        """main.py can create_app without error."""
        from hua_agent.main import app
        assert app is not None
        assert app.title == "花卉研究 Agent API"

    def test_config_settings(self):
        """config.py loads from .env.example."""
        from hua_agent.config import Settings
        s = Settings(_env_file=".env.example")
        assert s.port == 5000
        assert s.host == "0.0.0.0"
