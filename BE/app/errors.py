"""에러 응답 형식 (CONVENTIONS §10).

{ "error": { "code": ..., "message": ..., "details": [...] } }

| HTTP | code               |
| 400  | VALIDATION_FAILED  |
| 404  | NOT_FOUND          |
| 422  | NOT_COMPUTABLE     |
| 500  | INTERNAL_ERROR     |
"""


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, details: list | None = None):
        self.status = status
        self.code = code
        self.message = message
        self.details = details or []

    def body(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


def validation_failed(message: str, details: list | None = None) -> AppError:
    return AppError(400, "VALIDATION_FAILED", message, details)


def not_found(message: str) -> AppError:
    return AppError(404, "NOT_FOUND", message)


def install_handlers(app) -> None:
    """모든 에러가 위 형식으로 나가도록 FastAPI에 등록합니다."""
    from fastapi import Request
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse
    from starlette.exceptions import HTTPException

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status, content=exc.body())

    @app.exception_handler(RequestValidationError)
    async def _bad_request(_: Request, exc: RequestValidationError):
        details = [
            {
                "column": ".".join(str(x) for x in e.get("loc", [])[1:]),
                "value": str(e.get("input", "")),
                "message": e.get("msg", ""),
            }
            for e in exc.errors()
        ]
        err = validation_failed("요청 값이 올바르지 않습니다", details)
        return JSONResponse(status_code=400, content=err.body())

    @app.exception_handler(HTTPException)
    async def _http_error(_: Request, exc: HTTPException):
        if exc.status_code == 404:
            err = not_found("요청한 주소를 찾을 수 없습니다")
        else:
            err = AppError(exc.status_code, "INTERNAL_ERROR", str(exc.detail))
        return JSONResponse(status_code=err.status, content=err.body())

    @app.exception_handler(Exception)
    async def _unknown(_: Request, exc: Exception):
        err = AppError(500, "INTERNAL_ERROR", "서버 내부 오류가 발생했습니다")
        return JSONResponse(status_code=500, content=err.body())
