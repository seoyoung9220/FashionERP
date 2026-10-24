"""앱의 시작점. 실행: uvicorn app.main:app --reload  →  http://localhost:8000/docs

여기서 하는 일
1. 앱 시작 시 테이블 만들기 + DB가 비어 있으면 데모 데이터 자동 적재
2. 에러 응답 형식 통일 (CONVENTIONS §10)
3. 프론트엔드(localhost)에서 호출할 수 있게 허용 (CORS)
4. routers 폴더의 API 주소들을 등록
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import connect, init_db
from app.errors import install_handlers
from app.importers.loader import seed_if_empty
from app.routers import imports, inventory, quality, returns, summary, tasks


@asynccontextmanager
async def lifespan(_: FastAPI):
    conn = connect()
    init_db(conn)
    seed_if_empty(conn)
    conn.close()
    yield


app = FastAPI(title="FashionERP API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",   # 로컬 프론트 개발 서버
    allow_methods=["*"],
    allow_headers=["*"],
)

install_handlers(app)

app.include_router(imports.router)
app.include_router(returns.router)
app.include_router(tasks.router)
app.include_router(quality.router)
app.include_router(inventory.router)
app.include_router(summary.router)


@app.get("/health", tags=["상태"])
def health():
    return {"status": "ok"}
