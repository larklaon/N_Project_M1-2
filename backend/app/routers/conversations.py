from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Response

from app.dependencies import owner, store
from app.models import Conversation, ConversationInput, ConversationItem
from app.store import now

router = APIRouter(prefix="/api/conversations", tags=["대화 기록"])
Store = Annotated[object, Depends(store)]
Owner = Annotated[str, Depends(owner)]


def find_conversation(db, id, session):
    record = db.get("conversations", str(id))
    if record is None or record.get("owner") != session:
        raise HTTPException(404, "대화를 찾을 수 없습니다. 같은 브라우저에서 저장한 대화인지 확인하세요.")
    return record


@router.post("", status_code=201, response_model=Conversation, summary="대화 수동 저장 · 새 사본")
def save_conversation(payload: ConversationInput, db: Store, session: Owner):
    timestamp, id = now(), str(uuid4())
    record = {**payload.model_dump(), "id": id, "owner": session, "revision": 1,
              "created_at": timestamp, "updated_at": timestamp}
    db.save("conversations", id, record)
    return record


@router.get("", response_model=list[ConversationItem], summary="현재 브라우저의 대화 목록 · messages 제외")
def list_conversations(db: Store, session: Owner):
    records = sorted(db.list("conversations", owner=session), key=lambda r: r["updated_at"], reverse=True)
    return [{**r, "message_count": len(r["messages"])} for r in records]


@router.get("/{id}", response_model=Conversation, summary="특정 대화의 전체 messages 불러오기")
def get_conversation(id: UUID, db: Store, session: Owner):
    return find_conversation(db, id, session)


@router.delete("/{id}", status_code=204, summary="대화 삭제")
def delete_conversation(id: UUID, db: Store, session: Owner):
    db.delete("conversations", str(id), owner=session)
    return Response(status_code=204)
