from langchain.agents import create_agent
from langchain.agents.middleware.summarization import SummarizationMiddleware


def create_stage2_agent(model, tavily_tool, checkpointer):
    return create_agent(
        model=model,
        tools=[tavily_tool],
        checkpointer=checkpointer,
        system_prompt=(
            "你是一个专业的花卉研究助手。"
            "对话历史中已有一份结构化花卉报告（包含形态结构、植物分类、生长习性、"
            "花期规律、气味与特征、繁殖方式、使用价值、文化寓意等维度）。"
            "请基于已有报告回答用户的追问。如果需要更多信息或用户询问其他花卉，"
            "可以使用 Tavily 搜索工具查找新资料。"
        ),
        middleware=[
            SummarizationMiddleware(
                model=model,
                trigger=("tokens", 51200),
                keep=("messages", 20),
            ),
        ],
    )
