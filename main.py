import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from database import engine, Base, SessionLocal
from models import User, UserRole
from auth import hash_password
from routes import auth as auth_router
from routes import problems as problems_router
from routes import submissions as submissions_router
from routes import users as users_router
from routes import admin as admin_router

app = FastAPI(title="CodeBench")
templates = Jinja2Templates(directory="templates")

app.include_router(auth_router.router)
app.include_router(problems_router.router)
app.include_router(submissions_router.router)
app.include_router(users_router.router)
app.include_router(admin_router.router)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    _seed_admin()


def _seed_admin():
    db = SessionLocal()
    try:
        admin_username = os.getenv("ADMIN_USERNAME", "admin")
        admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
        admin_email = os.getenv("ADMIN_EMAIL", "admin@codebench.local")
        existing = db.query(User).filter(User.role == UserRole.admin).first()
        if not existing:
            admin = User(
                username=admin_username,
                email=admin_email,
                password_hash=hash_password(admin_password),
                role=UserRole.admin,
            )
            db.add(admin)
            db.commit()
            print(f"[CodeBench] Admin created — username: {admin_username}, password: lol xd")
    finally:
        db.close()


@app.exception_handler(404)
async def not_found(request: Request, exc):
    from auth import decode_token
    token = request.cookies.get("access_token")
    user = None
    if token:
        payload = decode_token(token)
        if payload:
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.id == int(payload["sub"])).first()
            finally:
                db.close()
    return templates.TemplateResponse(
        request, "404.html", {"user": user}, status_code=404
    )


@app.exception_handler(403)
async def forbidden(request: Request, exc):
    return HTMLResponse("<h1>403 — Access Denied</h1>", status_code=403)
