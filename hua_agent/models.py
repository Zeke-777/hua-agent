from typing import Annotated

from pydantic import BeforeValidator, BaseModel

_FIELD_MAX = 100


def _truncate(v: str) -> str:
    if v is None:
        return ""
    return v[:_FIELD_MAX]


_Field = Annotated[str, BeforeValidator(_truncate)]


class FlowerInfo(BaseModel):
    """花卉结构化信息报告。每个内容字段最长100字，自动截断。"""

    名称: str
    形态结构: _Field
    植物分类: _Field
    生长习性: _Field
    花期规律: _Field
    气味与特征: _Field
    繁殖方式: _Field
    使用价值: _Field
    文化寓意: _Field
    参考来源: str


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ResearchResponse(BaseModel):
    """研究/上传接口的结构化响应。"""
    ok: bool
    stage: int
    session_id: str
    flower_name: str
    flower_info: dict | None = None
    image_url: str | None = None
