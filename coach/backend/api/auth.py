from fastapi import APIRouter, Cookie, Depends, Request, Response

from ..core.models import Err
from ..core.security import SESSION_TTL
from .deps import AppState, client_ip, err, get_state
from .schemas import LoginRequest, RegisterRequest

SESSION_COOKIE = "session"
AUTH_ATTEMPTS, AUTH_WINDOW = 10, 300  # sign-in tries per IP per 5 minutes

router = APIRouter(prefix="/api", tags=["auth"])


def _sign_in(state: AppState, response: Response, username: str) -> dict:
    token = state.sessions.create(username)
    response.set_cookie(
        SESSION_COOKIE, token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True, samesite="lax", secure=state.secure_cookies, path="/",
    )
    return {"username": username}


@router.get("/auth")
def auth_status(state: AppState = Depends(get_state), session: str | None = Cookie(default=None)):
    username = state.sessions.resolve(session)
    return {
        "signed_in": username is not None,
        "username": username,
    }


@router.post("/register")
def register(req: RegisterRequest, request: Request, response: Response,
             state: AppState = Depends(get_state)):
    if not state.limiter.allow(f"auth:{client_ip(request)}", AUTH_ATTEMPTS, AUTH_WINDOW):
        return err("too many attempts — try again in a few minutes", status=429)
    result = state.users.register(req.username, req.password)
    if isinstance(result, Err):
        return err(result.message)
    return _sign_in(state, response, req.username)


@router.post("/login")
def login(req: LoginRequest, request: Request, response: Response,
          state: AppState = Depends(get_state)):
    if not state.limiter.allow(f"auth:{client_ip(request)}", AUTH_ATTEMPTS, AUTH_WINDOW):
        return err("too many attempts — try again in a few minutes", status=429)
    if not state.users.verify(req.username, req.password):
        return err("wrong username or password", status=401)
    return _sign_in(state, response, req.username)


@router.post("/logout")
def logout(response: Response, state: AppState = Depends(get_state),
           session: str | None = Cookie(default=None)):
    state.sessions.revoke(session)
    response.delete_cookie(
        SESSION_COOKIE, path="/", httponly=True, samesite="lax", secure=state.secure_cookies,
    )
    return {"signed_out": True}
