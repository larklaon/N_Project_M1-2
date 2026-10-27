"""Run once from backend/: python -m scripts.seed. Existing dates are preserved."""
from fastapi import HTTPException

from app.config import Settings
from app.store import FirestoreStore, initial_records


def main():
    settings = Settings.from_env()
    if settings.demo:
        raise SystemExit("DEMO_MODE=false로 실행하세요. 데모 데이터는 앱 시작 시 자동 준비됩니다.")
    db, added, skipped = FirestoreStore(settings), 0, 0
    try:
        for record in initial_records():
            try:
                db.save("data", record["id"], record)
                added += 1
            except HTTPException as exc:
                if exc.status_code != 409:
                    raise
                skipped += 1
        print(f"Firestore 초기화 완료: 추가 {added}개, 기존 데이터 유지 {skipped}개")
    finally:
        db.close()


if __name__ == "__main__":
    main()
