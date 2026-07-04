"""Verify all modules can be imported."""

from unittest.mock import MagicMock


def test_models_re_exports():
    """models.py re-exports from schemas.py."""
    from hua_agent.models import ChatRequest, FlowerInfo, ResearchResponse
    assert FlowerInfo is not None
    assert ChatRequest is not None
    assert ResearchResponse is not None


def test_stage2_workflow_import():
    """stage2 workflow module can be imported."""
    from hua_agent.workflows.stage2 import create_stage2_agent
    assert create_stage2_agent is not None
