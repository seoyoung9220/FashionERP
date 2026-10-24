"""요청 모양 정의 (Pydantic).

요청 JSON이 이 모양과 다르면 FastAPI가 자동으로 400 VALIDATION_FAILED 를 돌려줍니다.
응답은 api.md 예시와 키·타입이 똑같도록 services 에서 dict로 만듭니다.
"""
from pydantic import BaseModel, ConfigDict, Field


class Period(BaseModel):
    from_: str = Field(alias="from", pattern=r"^\d{4}-\d{2}-\d{2}$")   # from 은 파이썬 예약어라 alias 사용
    to: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")

    model_config = ConfigDict(populate_by_name=True)

    def as_dict(self) -> dict:
        return {"from": self.from_, "to": self.to}


class AnalyzeRequest(BaseModel):
    product_id: str
    period: Period


class TaskSource(BaseModel):
    type: str
    ref: str


class TaskCreate(BaseModel):
    product_id: str
    title: str
    type: str
    assignee: str | None = None
    due_date: str | None = None
    source: TaskSource | None = None


class TaskUpdate(BaseModel):
    """변경 가능: status · assignee · due_date · title"""
    status: str | None = None
    assignee: str | None = None
    due_date: str | None = None
    title: str | None = None
