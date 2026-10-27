import hashlib
from typing import Annotated

from fastapi import Header, Request


def store(request: Request):
    return request.app.state.store


def owner(x_session_id: Annotated[str, Header(min_length=32, max_length=128,
          description="브라우저가 생성하는 무작위 세션 키. Swagger에서는 32자 이상 임의 값을 입력하세요.")]):
    return hashlib.sha256(x_session_id.encode()).hexdigest()
