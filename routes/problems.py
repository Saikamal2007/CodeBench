from fastapi import APIRouter, Request, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import User, Problem, Submission
from auth import decode_token

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def get_current_user(request: Request, db: Session):
    token = request.cookies.get("access_token")
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    return db.query(User).filter(User.id == int(payload["sub"])).first()


@router.get("/", response_class=HTMLResponse)
def problem_list(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    problems = db.query(Problem).filter(Problem.is_visible == True).order_by(Problem.id).all()

    solved_ids = set()
    attempted_ids = set()
    if user:
        subs = db.query(Submission).filter(Submission.user_id == user.id).all()
        for s in subs:
            if s.verdict == "accepted":
                solved_ids.add(s.problem_id)
            else:
                attempted_ids.add(s.problem_id)

    return templates.TemplateResponse(request, "index.html", {
        "user": user,
        "problems": problems,
        "solved_ids": solved_ids,
        "attempted_ids": attempted_ids,
    })


@router.get("/problems/{problem_id}", response_class=HTMLResponse)
def problem_detail(problem_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    problem = db.query(Problem).filter(Problem.id == problem_id, Problem.is_visible == True).first()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")

    sample_cases = [tc for tc in problem.test_cases if tc.is_sample]
    user_submissions = []
    if user:
        user_submissions = (
            db.query(Submission)
            .filter(Submission.user_id == user.id, Submission.problem_id == problem_id)
            .order_by(Submission.created_at.desc())
            .limit(5)
            .all()
        )

    return templates.TemplateResponse(request, "problems/detail.html", {
        "user": user,
        "problem": problem,
        "sample_cases": sample_cases,
        "user_submissions": user_submissions,
        "error": None,
    })


@router.post("/problems/{problem_id}/submit")
async def submit_solution(
    problem_id: int,
    request: Request,
    language: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    problem = db.query(Problem).filter(Problem.id == problem_id, Problem.is_visible == True).first()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")

    ext_map = {"python": ".py", "cpp": ".cpp", "java": ".java"}
    expected_ext = ext_map.get(language)
    if not expected_ext or not file.filename.endswith(expected_ext):
        sample_cases = [tc for tc in problem.test_cases if tc.is_sample]
        return templates.TemplateResponse(request, "problems/detail.html", {
            "user": user,
            "problem": problem,
            "sample_cases": sample_cases,
            "user_submissions": [],
            "error": f"Please upload a {expected_ext} file for {language}",
        })

    code_bytes = await file.read()
    try:
        code = code_bytes.decode("utf-8")
    except UnicodeDecodeError:
        code = code_bytes.decode("latin-1")

    submission = Submission(
        user_id=user.id,
        problem_id=problem_id,
        language=language,
        code=code,
        verdict="pending",
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    submission_id = submission.id

    # Run judging in background so the user is redirected immediately
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from judge.runner import judge_submission
    from database import SessionLocal

    test_cases = list(problem.test_cases)
    time_limit_ms = problem.time_limit_ms
    memory_limit_mb = problem.memory_limit_mb

    def run_judge():
        verdict, runtime_ms = judge_submission(
            language=language,
            code=code,
            test_cases=test_cases,
            time_limit_ms=time_limit_ms,
            memory_limit_mb=memory_limit_mb,
        )
        judge_db = SessionLocal()
        try:
            sub = judge_db.query(Submission).filter(Submission.id == submission_id).first()
            if sub:
                sub.verdict = verdict
                sub.runtime_ms = runtime_ms
                judge_db.commit()
        finally:
            judge_db.close()

    loop = asyncio.get_event_loop()
    loop.run_in_executor(ThreadPoolExecutor(max_workers=1), run_judge)

    return RedirectResponse(f"/submissions/{submission_id}", status_code=302)
