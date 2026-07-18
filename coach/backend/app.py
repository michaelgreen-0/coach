import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import auth, study, tutor
from .api.deps import AppState, SubjectState
from .core.config import load_config
from .core.limits import RateLimiter
from .core.models import Err
from .core.security import Database, SessionStore, UserStore, migrate_json_files
from .services import tutor as tutor_service
from .services.storage import load_bank

STATIC_DIR = Path(__file__).resolve().parent.parent / "frontend" / "static"
SECURE_COOKIES_ENV = "COACH_SECURE_COOKIES"


def _env_flag(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def create_app(config_path: Path | None = None) -> FastAPI:
    cfg_result = load_config(config_path)
    if isinstance(cfg_result, Err):
        raise RuntimeError(cfg_result.message)
    cfg = cfg_result.value

    states: dict[str, SubjectState] = {}
    for subj in cfg.subjects:
        bank_result = load_bank(subj.bank_path)
        if isinstance(bank_result, Err):
            raise RuntimeError(f"subject '{subj.name}': {bank_result.message}")
        states[subj.slug] = SubjectState(
            subject=subj,
            bank=bank_result.value,
            by_id={q.id: q for q in bank_result.value.questions},
        )

    db = Database(cfg.data_dir / "coach.db")
    migrate_json_files(db, cfg.data_dir)

    app_state = AppState(
        cfg=cfg,
        states=states,
        default_slug=cfg.subjects[0].slug,
        users=UserStore(db),
        sessions=SessionStore(db),
        secure_cookies=_env_flag(os.environ.get(SECURE_COOKIES_ENV)),
        tutor_on=cfg.tutor is not None and tutor_service.tutor_available(cfg.tutor),
        limiter=RateLimiter(),
    )

    app = FastAPI(title="coach")
    app.state.app_state = app_state

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(request, exc):
        # keep one error envelope everywhere: {"error": ...}
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    app.include_router(auth.router)
    app.include_router(study.router)
    app.include_router(tutor.router)

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def main() -> None:
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
