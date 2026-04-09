from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import User, Submission
from auth import decode_token

router = APIRouter()
templates = Jinja2Templates(directory="templates")

VERDICT_DISPLAY = {
    "accepted": "Accepted",
    "wrong_answer": "Wrong Answer",
    "time_limit_exceeded": "Time Limit Exceeded",
    "memory_limit_exceeded": "Memory Limit Exceeded",
    "runtime_error": "Runtime Error",
    "compilation_error": "Compilation Error",
    "pending": "Pending",
}

VERDICT_COLOR = {
    "accepted": "success",
    "wrong_answer": "danger",
    "time_limit_exceeded": "warning",
    "memory_limit_exceeded": "warning",
    "runtime_error": "danger",
    "compilation_error": "secondary",
    "pending": "info",
}


def get_current_user(request: Request, db: Session):
    token = request.cookies.get("access_token")
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    return db.query(User).filter(User.id == int(payload["sub"])).first()


@router.get("/submissions", response_class=HTMLResponse)
def my_submissions(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    submissions = (
        db.query(Submission)
        .filter(Submission.user_id == user.id)
        .order_by(Submission.created_at.desc())
        .all()
    )

    return templates.TemplateResponse(request, "submissions/list.html", {
        "user": user,
        "submissions": submissions,
        "verdict_display": VERDICT_DISPLAY,
        "verdict_color": VERDICT_COLOR,
    })


@router.get("/submissions/{submission_id}", response_class=HTMLResponse)
def submission_detail(submission_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if submission.user_id != user.id and user.role.value != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    return templates.TemplateResponse(request, "submissions/detail.html", {
        "user": user,
        "submission": submission,
        "verdict_display": VERDICT_DISPLAY,
        "verdict_color": VERDICT_COLOR,
    })
