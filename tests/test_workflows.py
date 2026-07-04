"""Workflow tests: verify Stage1 graph structure and error handling."""

from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from hua_agent.workflows.stage1 import create_stage1_workflow


@pytest.fixture
def mock_model():
    """Mock LLM that returns a valid FlowerInfo."""
    model = MagicMock()
    structured = MagicMock()
    # Return a valid FlowerInfo dict via structured output
    from hua_agent.schemas import FlowerInfo

    flower_info = FlowerInfo(
        **{
            "名称": "玫瑰",
            "形态结构": "灌木",
            "植物分类": "蔷薇科",
            "生长习性": "喜阳",
            "花期规律": "5-7月",
            "气味与特征": "芳香",
            "繁殖方式": "扦插",
            "使用价值": "观赏",
            "文化寓意": "爱情",
            "参考来源": "https://example.com",
        }
    )
    structured.invoke.return_value = flower_info
    model.with_structured_output.return_value = structured
    return model


@pytest.fixture
def mock_tavily():
    """Mock Tavily search tool."""
    tool = MagicMock()
    tool.invoke.return_value = '[{"content": "玫瑰是蔷薇科植物", "url": "https://example.com"}]'
    return tool


@pytest.fixture
def checkpointer():
    """Use None checkpointer — no persistence needed for unit tests."""
    return None


class TestStage1Workflow:
    def test_graph_structure(self, mock_model, mock_tavily, checkpointer):
        """Compiled graph has 3 nodes: search, extract, report."""
        graph = create_stage1_workflow(mock_model, mock_tavily, checkpointer)
        nodes = graph.get_graph().nodes
        # Should have at least search, extract, report + __start__, __end__
        assert "search" in nodes
        assert "extract" in nodes
        assert "report" in nodes

    def test_search_node_calls_tavily(self, mock_model, mock_tavily, checkpointer):
        """Search node invokes tavily_tool.invoke once."""
        graph = create_stage1_workflow(mock_model, mock_tavily, checkpointer)
        result = graph.invoke(
            {"messages": [HumanMessage(content="玫瑰")]},
            {"configurable": {"thread_id": "test-1"}},
        )
        mock_tavily.invoke.assert_called_once()
        assert "report" in result
        assert result["report"]["名称"] == "玫瑰"

    def test_empty_flower_info_does_not_crash(self, mock_model, mock_tavily, checkpointer):
        """When LLM returns empty result, report node handles it gracefully."""
        # Make structured model return minimal FlowerInfo
        from hua_agent.schemas import FlowerInfo

        empty_info = FlowerInfo(
            **{
                "名称": "", "形态结构": "", "植物分类": "",
                "生长习性": "", "花期规律": "", "气味与特征": "",
                "繁殖方式": "", "使用价值": "", "文化寓意": "",
                "参考来源": "",
            }
        )
        structured = mock_model.with_structured_output.return_value
        structured.invoke.return_value = empty_info

        graph = create_stage1_workflow(mock_model, mock_tavily, checkpointer)
        result = graph.invoke(
            {"messages": [HumanMessage(content="unknown")]},
            {"configurable": {"thread_id": "test-2"}},
        )
        assert "report" in result
        # Should have at least one AI message from report node
        messages = result.get("messages", [])
        ai_messages = [m for m in messages if isinstance(m, AIMessage)]
        assert len(ai_messages) >= 1

    def test_tavily_exception_does_not_crash(self, mock_model, mock_tavily, checkpointer):
        """When Tavily throws, search node returns fallback text."""
        mock_tavily.invoke.side_effect = Exception("Network error")

        graph = create_stage1_workflow(mock_model, mock_tavily, checkpointer)
        result = graph.invoke(
            {"messages": [HumanMessage(content="玫瑰")]},
            {"configurable": {"thread_id": "test-3"}},
        )
        # Should not crash, search_raw should be fallback text
        assert "report" in result
        # Graph should complete without exception
        assert result.get("search_raw", "") != ""

    def test_tavily_called_with_query_containing_flower_name(
        self, mock_model, mock_tavily, checkpointer
    ):
        """Tavily is called with a query that includes the flower name."""
        graph = create_stage1_workflow(mock_model, mock_tavily, checkpointer)
        graph.invoke(
            {"messages": [HumanMessage(content="牡丹")]},
            {"configurable": {"thread_id": "test-4"}},
        )
        call_args = mock_tavily.invoke.call_args[0][0]
        assert "牡丹" in call_args
