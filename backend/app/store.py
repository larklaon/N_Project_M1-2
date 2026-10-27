"""Same contract for Firestore and an explicit, single-process local demo store."""
import copy
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from fastapi import HTTPException

from app.config import ROOT, Settings


def now():
    return datetime.now(timezone.utc).isoformat()


def initial_records():
    path = ROOT / "data" / "raw" / "day.csv"
    if hashlib.sha256(path.read_bytes()).hexdigest() != "a6bcf826782d3c0fbfdcbeead17cd0884185a0dafe8ff10cd48a874ee7ba18be":
        raise ValueError("원본 데이터 체크섬이 일치하지 않습니다.")
    timestamp = now()
    with path.open() as stream:
        rows = [{"id": r["dteday"], "date": r["dteday"], "value": int(r["cnt"]),
                 "memo": "UCI Bike Sharing · 원본 일별 총 대여 건수",
                 "created_at": timestamp, "updated_at": timestamp} for r in csv.DictReader(stream)]
    if len(rows) != 731 or len({r["date"] for r in rows}) != 731:
        raise ValueError("초기 데이터는 고유한 날짜의 731행이어야 합니다.")
    return rows


def check_write(current, expected):
    if expected is None and current is not None:
        raise HTTPException(409, "이미 저장된 항목입니다. 날짜나 대화 목록을 확인하세요.")
    if expected is not None:
        if current is None:
            raise HTTPException(404, "항목을 찾을 수 없습니다.")
        if current.get("revision") != expected:
            raise HTTPException(409, "다른 요청에서 대화가 변경되었습니다. 대화를 다시 불러오세요.")


class LocalStore:
    def __init__(self, path: Path, seed=True):
        self.path, self.lock = path, RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            self.state = json.loads(path.read_text())
        else:
            self.state = {"data": {r["id"]: r for r in initial_records()} if seed else {}, "conversations": {}}
            self._flush()

    def _flush(self):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.path)

    def list(self, collection, owner=None):
        with self.lock:
            return copy.deepcopy([r for r in self.state[collection].values()
                                  if owner is None or r.get("owner") == owner])

    def get(self, collection, id):
        with self.lock:
            return copy.deepcopy(self.state[collection].get(id))

    def save(self, collection, id, value, expected=None):
        with self.lock:
            check_write(self.state[collection].get(id), expected)
            self.state[collection][id] = copy.deepcopy(value)
            self._flush()

    def move_data(self, id, value):
        with self.lock:
            old = self.state["data"].get(id)
            if old is None:
                raise HTTPException(404, "데이터를 찾을 수 없습니다.")
            if id != value["id"] and value["id"] in self.state["data"]:
                raise HTTPException(409, "해당 날짜의 데이터가 이미 있습니다.")
            value["created_at"] = old["created_at"]
            del self.state["data"][id]
            self.state["data"][value["id"]] = copy.deepcopy(value)
            self._flush()

    def delete(self, collection, id, owner=None):
        with self.lock:
            current = self.state[collection].get(id)
            if current is None or (owner and current.get("owner") != owner):
                raise HTTPException(404, "항목을 찾을 수 없습니다.")
            del self.state[collection][id]
            self._flush()


class FirestoreStore:
    def __init__(self, settings: Settings):
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not settings.firebase_json and not settings.firebase_path:
            raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON 또는 FIREBASE_SERVICE_ACCOUNT_PATH를 설정하세요.")
        credential = (credentials.Certificate(json.loads(settings.firebase_json)) if settings.firebase_json
                      else credentials.Certificate(settings.firebase_path))
        app = firebase_admin.initialize_app(credential, name="bikewise-" + __import__("uuid").uuid4().hex)
        self.db, self.firebase_app = firestore.client(app), app

    def close(self):
        import firebase_admin
        self.db.close()
        firebase_admin.delete_app(self.firebase_app)

    def list(self, collection, owner=None):
        from google.cloud.firestore_v1.base_query import FieldFilter
        query = self.db.collection(collection)
        if owner:
            query = query.where(filter=FieldFilter("owner", "==", owner))
        return [s.to_dict() for s in query.stream(timeout=15)]

    def get(self, collection, id):
        return self.db.collection(collection).document(id).get(timeout=15).to_dict()

    def save(self, collection, id, value, expected=None):
        from google.cloud import firestore
        ref = self.db.collection(collection).document(id)

        @firestore.transactional
        def write(transaction):
            check_write(ref.get(transaction=transaction).to_dict(), expected)
            transaction.set(ref, value)

        write(self.db.transaction())

    def move_data(self, id, value):
        from google.cloud import firestore
        old_ref = self.db.collection("data").document(id)
        new_ref = self.db.collection("data").document(value["id"])

        @firestore.transactional
        def move(transaction):
            old = old_ref.get(transaction=transaction).to_dict()
            if old is None:
                raise HTTPException(404, "데이터를 찾을 수 없습니다.")
            if id != value["id"] and new_ref.get(transaction=transaction).exists:
                raise HTTPException(409, "해당 날짜의 데이터가 이미 있습니다.")
            value["created_at"] = old["created_at"]
            if id != value["id"]:
                transaction.delete(old_ref)
            transaction.set(new_ref, value)

        move(self.db.transaction())

    def delete(self, collection, id, owner=None):
        from google.cloud import firestore
        ref = self.db.collection(collection).document(id)

        @firestore.transactional
        def remove(transaction):
            current = ref.get(transaction=transaction).to_dict()
            if current is None or (owner and current.get("owner") != owner):
                raise HTTPException(404, "항목을 찾을 수 없습니다.")
            transaction.delete(ref)

        remove(self.db.transaction())
