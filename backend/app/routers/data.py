from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.dependencies import store
from app.models import DataInput, DataList, DataRecord, Summary
from app.services.summary import summarize
from app.store import now

router = APIRouter(prefix="/api/data", tags=["데이터"])
Store = Annotated[object, Depends(store)]


@router.get("/summary", response_model=Summary, summary="현재 DB 전체 데이터 요약")
def summary(db: Store):
    return summarize(db.list("data"))


@router.get("", response_model=DataList, summary="데이터 목록 · 날짜 내림차순")
def list_data(db: Store, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
              start: date | None = None, end: date | None = None):
    if start and end and start > end:
        raise HTTPException(422, "시작일은 종료일보다 늦을 수 없습니다.")
    rows = sorted([r for r in db.list("data")
                   if (not start or r["date"] >= start.isoformat())
                   and (not end or r["date"] <= end.isoformat())], key=lambda r: r["date"], reverse=True)
    return {"items": rows[offset:offset + limit], "total": len(rows), "offset": offset, "limit": limit}


@router.post("", response_model=DataRecord, status_code=201, summary="날짜별 대여 기록 추가")
def create_data(payload: DataInput, db: Store):
    timestamp = now()
    row = {**payload.model_dump(mode="json"), "id": payload.date.isoformat(),
           "created_at": timestamp, "updated_at": timestamp}
    db.save("data", row["id"], row)
    return row


@router.put("/{id}", response_model=DataRecord, summary="날짜·건수·메모 수정")
def update_data(id: date, payload: DataInput, db: Store):
    row = {**payload.model_dump(mode="json"), "id": payload.date.isoformat(), "updated_at": now()}
    db.move_data(id.isoformat(), row)
    return row


@router.delete("/{id}", status_code=204, summary="날짜별 데이터 삭제")
def delete_data(id: date, db: Store):
    db.delete("data", id.isoformat())
    return Response(status_code=204)
