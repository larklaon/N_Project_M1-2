from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DataInput(InputModel):
    date: date
    value: int = Field(ge=0, le=10_000_000, strict=True, description="하루 총 대여 건수")
    memo: str = Field(default="", max_length=500)


class DataRecord(DataInput):
    id: str
    created_at: str
    updated_at: str


class DataList(BaseModel):
    items: list[DataRecord]
    total: int
    offset: int
    limit: int


class Message(InputModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class ConversationInput(InputModel):
    title: str = Field(min_length=1, max_length=80)
    messages: list[Message] = Field(min_length=1, max_length=80)

    @model_validator(mode="after")
    def bounded_document(self):
        if sum(len(m.content.encode("utf-8")) for m in self.messages) > 600_000:
            raise ValueError("대화의 전체 본문은 UTF-8 기준 600KB 이하여야 합니다.")
        return self


class Conversation(BaseModel):
    id: str
    title: str
    messages: list[Message]
    created_at: str
    updated_at: str
    revision: int


class ConversationItem(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int


class ChatInput(InputModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: UUID | None = None


class Summary(BaseModel):
    period: str | None
    count: int
    metrics: dict
    trend: str
    recent: dict
    monthly: list[dict]
    annual: list[dict]
    source: str
    unit: str = "건/일"
    as_of: str | None


class ChatResult(BaseModel):
    conversation: Conversation
    answer: str
    summary: Summary
    demo: bool
