import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph import MessagesState

from .models import FlowerInfo

_logger = logging.getLogger(__name__)


class Stage1State(MessagesState):
    flower_name: str
    search_raw: str
    report: dict


def _search_node(tavily_tool):
    def search_node(state: Stage1State) -> dict:
        last_msg = state["messages"][-1]
        flower_name = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

        query = f"{flower_name} 花卉 详细介绍 形态结构 植物分类 生长习性 花期规律 气味特征 繁殖方式 使用价值 文化寓意"
        try:
            result = tavily_tool.invoke(query)
            search_raw = result if isinstance(result, str) else str(result)
        except Exception:
            _logger.exception("Tavily 搜索失败，使用回退")
            search_raw = "（搜索服务暂时不可用，请基于已有知识回答）"

        return {"flower_name": flower_name, "search_raw": search_raw}

    return search_node


def _extract_node(model):
    structured_model = model.with_structured_output(FlowerInfo, method="function_calling")

    def extract_node(state: Stage1State) -> dict:
        messages = [
            SystemMessage(
                content=(
                    "你是一个专业的花卉研究助手。请根据以下搜索结果，"
                    "提取花卉的结构化信息。每个字段不超过100字。"
                    "参考来源字段汇总所有使用的URL，每行格式: 数字. URL — 类别标签。"
                )
            ),
            HumanMessage(
                content=f"花卉名称: {state['flower_name']}\n\n搜索结果:\n{state['search_raw']}"
            ),
        ]
        try:
            result = structured_model.invoke(messages)
            return {"report": result.model_dump()}
        except Exception:
            _logger.exception("LLM 结构化输出失败，使用空报告回退")
            fallback = {
                "名称": state.get("flower_name", ""),
                "形态结构": "", "植物分类": "", "生长习性": "",
                "花期规律": "", "气味与特征": "", "繁殖方式": "",
                "使用价值": "", "文化寓意": "", "参考来源": "",
            }
            return {"report": fallback}

    return extract_node


def _report_node():
    def report_node(state: Stage1State) -> dict:
        r = state["report"]
        text = (
            f"## {r.get('名称', '')} 结构化研究报告\n\n"
            f"**形态结构**: {r.get('形态结构', '')}\n"
            f"**植物分类**: {r.get('植物分类', '')}\n"
            f"**生长习性**: {r.get('生长习性', '')}\n"
            f"**花期规律**: {r.get('花期规律', '')}\n"
            f"**气味与特征**: {r.get('气味与特征', '')}\n"
            f"**繁殖方式**: {r.get('繁殖方式', '')}\n"
            f"**使用价值**: {r.get('使用价值', '')}\n"
            f"**文化寓意**: {r.get('文化寓意', '')}\n\n"
            f"**参考来源**:\n{r.get('参考来源', '')}"
        )
        return {"messages": [AIMessage(content=text)]}

    return report_node


def create_stage1_workflow(model, tavily_tool, checkpointer):
    workflow = StateGraph(Stage1State)
    workflow.add_node("search", _search_node(tavily_tool))
    workflow.add_node("extract", _extract_node(model))
    workflow.add_node("report", _report_node())
    workflow.add_edge("search", "extract")
    workflow.add_edge("extract", "report")
    workflow.add_edge("report", END)
    workflow.set_entry_point("search")
    return workflow.compile(checkpointer=checkpointer)
