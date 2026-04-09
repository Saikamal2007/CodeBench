from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
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


@router.get("/profile/{username}", response_class=HTMLResponse)
def user_profile(username: str, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    profile_user = db.query(User).filter(User.username == username).first()
    if not profile_user:
        raise HTTPException(status_code=404, detail="User not found")

    submissions = (
        db.query(Submission)
        .filter(Submission.user_id == profile_user.id)
        .order_by(Submission.created_at.desc())
        .all()
    )

    total = len(submissions)
    accepted = sum(1 for s in submissions if s.verdict == "accepted")
    solved_problems = len(set(s.problem_id for s in submissions if s.verdict == "accepted"))

    return templates.TemplateResponse(request, "profile.html", {
        "user": current_user,
        "profile_user": profile_user,
        "submissions": submissions,
        "total_submissions": total,
        "accepted_submissions": accepted,
        "solved_problems": solved_problems,
        "verdict_display": VERDICT_DISPLAY,
        "verdict_color": VERDICT_COLOR,
    })
