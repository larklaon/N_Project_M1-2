# Bikewise

공유자전거 일별 대여 기록을 관리하고 저장된 수치를 바탕으로 AI와 대화하는 교육용 웹 서비스.
사용자는 분석 과제 학습자와 평가자다. 핵심 작업은 질문, CRUD, 대화 재열람이다.
FastAPI, Firestore, Gemini 3.8 Flash API, 바닐라 HTML/CSS/JS. 백엔드는 Render, 프론트는 Vercel.
사용자 요청에 따라 과제 원문의 GPT API 대신 Gemini를 사용한다.
보너스 기능은 구현 범위에서 제외한다. 보고서는 README.md에 작성한다.
실제 서비스 연결과 로컬 데모는 명시적으로 구분한다. 과거 자료를 현재 자료로 표현하지 않는다.
