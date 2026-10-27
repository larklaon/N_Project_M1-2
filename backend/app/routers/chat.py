from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request

from app.dependencies import owner, store
from app.models import ChatInput, ChatResult
from app.routers.conversations import find_conversation
from app.services.summary import summarize
from app.store import now

router = APIRouter(tags=["AI 채팅"])


@router.post("/api/chat", response_model=ChatResult, summary="현재 요약 기반 AI 답변 및 대화 자동 저장")
def chat(payload: ChatInput, request: Request, db: Annotated[object, Depends(store)],
         session: Annotated[str, Depends(owner)]):
    old = find_conversation(db, payload.conversation_id, session) if payload.conversation_id else None
    history = list(old["messages"]) if old else []
    if len(history) > 78:
        raise HTTPException(422, "한 대화는 최대 40회 질문할 수 있습니다. 새 대화를 시작하세요.")
    summary = summarize(db.list("data"))
    messages = history + [{"role": "user", "content": payload.message}]
    answer = request.app.state.chat.answer(messages, summary)
    timestamp, id = now(), old["id"] if old else str(uuid4())
    record = {"id": id, "owner": session, "title": old["title"] if old else payload.message[:60],
              "messages": messages + [{"role": "assistant", "content": answer}],
              "created_at": old["created_at"] if old else timestamp, "updated_at": timestamp,
              "revision": old["revision"] + 1 if old else 1}
    if sum(len(m["content"].encode("utf-8")) for m in record["messages"]) > 600_000:
        raise HTTPException(422, "대화가 너무 깁니다. 새 대화를 시작하세요.")
    # A compare-and-set prevents an overlapping request from overwriting a saved reply.
    db.save("conversations", id, record, expected=old["revision"] if old else None)
    return {"conversation": record, "answer": answer, "summary": summary,
            "demo": request.app.state.settings.demo}
