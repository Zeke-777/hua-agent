"""Model tests: _truncate type safety (F7)."""
import pytest

from hua_agent.schemas import _truncate


class TestTruncate:
    """Verify _truncate handles all input types safely."""

    def test_none(self):
        """None returns empty string."""
        assert _truncate(None) == ""

    def test_normal_string(self):
        """Normal string is returned as-is."""
        assert _truncate("花卉名称") == "花卉名称"

    def test_int(self):
        """int is converted to string."""
        assert _truncate(12345) == "12345"

    def test_float(self):
        """float is converted to string."""
        result = _truncate(3.14159)
        assert isinstance(result, str)
        assert result.startswith("3.14")

    def test_list(self):
        """list is converted to string representation."""
        result = _truncate(["灌木", "高1-2米"])
        assert isinstance(result, str)
        assert "灌木" in result

    def test_long_string(self):
        """String longer than _FIELD_MAX (100) is truncated."""
        long_str = "a" * 200
        result = _truncate(long_str)
        assert len(result) == 100
        assert result == "a" * 100
