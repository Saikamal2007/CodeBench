from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db
from models import User, Problem, TestCase, Submission, UserRole, Difficulty
from auth import decode_token

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="templates")


def get_admin_user(request: Request, db: Session):
    token = request.cookies.get("access_token")
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user or user.role.value != "admin":
        return None
    return user


@router.get("", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    admin = get_admin_user(request, db)
    if not admin:
        return RedirectResponse("/login", status_code=302)
    total_users = db.query(User).count()
    total_problems = db.query(Problem).count()
    total_submissions = db.query(Submission).count()
    accepted = db.query(Submission).filter(Submission.verdict == "accepted").count()
    return templates.TemplateResponse(request, "admin/dashboard.html", {
        "user": admin,
        "total_users": total_users,
        "total_problems": total_problems,
        "total_submissions": total_submissions,
        "accepted_submissions": accepted,
    })


# ── Problems ──────────────────────────────────────────────────────────────────

@router.get("/problems", response_class=HTMLResponse)
def admin_problems(request: Request, db: Session = Depends(get_db)):
    admin = get_admin_user(request, db)
    if not admin:
        return RedirectResponse("/login", status_code=302)
    problems = db.query(Problem).order_by(Problem.id).all()
    return templates.TemplateResponse(request, "admin/problems.html", {
        "user": admin, "problems": problems
    })


@router.get("/problems/new", response_class=HTMLResponse)
def new_problem_form(request: Request, db: Session = Depends(get_db)):
    admin = get_admin_user(request, db)
    if not admin:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse(request, "admin/problem_form.html", {
        "user": admin, "problem": None, "error": None
    })


@router.post("/problems/new")
def create_problem(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    difficulty: str = Form(...),
    time_limit_ms: int = Form(1000),
    memory_limit_mb: int = Form(256),
    is_visible: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    admin = get_admin_user(request, db)
    if not admin:
        return RedirectResponse("/login", status_code=302)
    problem = Problem(
        title=title,
        description=description,
        difficulty=Difficulty(difficulty),
        time_limit_ms=time_limit_ms,
        memory_limit_mb=memory_limit_mb,
        is_visible=is_visible == "on",
        created_by=admin.id,
    )
    db.add(problem)
    db.commit()
    db.refresh(problem)
    return RedirectResponse(f"/admin/problems/{problem.id}/testcases", status_code=302)


@router.get("/problems/{problem_id}/edit", response_class=HTMLResponse)
def edit_problem_form(problem_id: int, request: Request, db: Session = Depends(get_db)):
    admin = get_admin_user(request, db)
    if not admin:
        return RedirectResponse("/login", status_code=302)
    problem = db.query(Problem).filter(Problem.id == problem_id).first()
    if not problem:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "admin/problem_form.html", {
        "user": admin, "problem": problem, "error": None
    })


@router.post("/problems/{problem_id}/edit")
def update_problem(
    problem_id: int,
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    difficulty: str = Form(...),
    time_limit_ms: int = Form(1000),
    memory_limit_mb: int = Form(256),
    is_visible: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    admin = get_admin_user(request, db)
    if not admin:
        return RedirectResponse("/login", status_code=302)
    problem = db.query(Problem).filter(Problem.id == problem_id).first()
    if not problem:
        raise HTTPException(status_code=404)
    problem.title = title
    problem.description = description
    problem.difficulty = Difficulty(difficulty)
    problem.time_limit_ms = time_limit_ms
    problem.memory_limit_mb = memory_limit_mb
    problem.is_visible = is_visible == "on"
    db.commit()
    return RedirectResponse("/admin/problems", status_code=302)


@router.post("/problems/{problem_id}/delete")
def delete_problem(problem_id: int, request: Request, db: Session = Depends(get_db)):
    admin = get_admin_user(request, db)
    if not admin:
        return RedirectResponse("/login", status_code=302)
    problem = db.query(Problem).filter(Problem.id == problem_id).first()
    if problem:
        db.delete(problem)
        db.commit()
    return RedirectResponse("/admin/problems", status_code=302)


# ── Test Cases ────────────────────────────────────────────────────────────────

@router.get("/problems/{problem_id}/testcases", response_class=HTMLResponse)
def admin_testcases(problem_id: int, request: Request, db: Session = Depends(get_db)):
    admin = get_admin_user(request, db)
    if not admin:
        return RedirectResponse("/login", status_code=302)
    problem = db.query(Problem).filter(Problem.id == problem_id).first()
    if not problem:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "admin/testcases.html", {
        "user": admin, "problem": problem, "test_cases": problem.test_cases
    })


@router.get("/problems/{problem_id}/testcases/new", response_class=HTMLResponse)
def new_testcase_form(problem_id: int, request: Request, db: Session = Depends(get_db)):
    admin = get_admin_user(request, db)
    if not admin:
        return RedirectResponse("/login", status_code=302)
    problem = db.query(Problem).filter(Problem.id == problem_id).first()
    if not problem:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "admin/testcase_form.html", {
        "user": admin, "problem": problem, "tc": None
    })


@router.post("/problems/{problem_id}/testcases/new")
def create_testcase(
    problem_id: int,
    request: Request,
    input: str = Form(""),
    expected_output: str = Form(...),
    is_sample: Optional[str] = Form(None),
    order_index: int = Form(0),
    db: Session = Depends(get_db),
):
    admin = get_admin_user(request, db)
    if not admin:
        return RedirectResponse("/login", status_code=302)
    tc = TestCase(
        problem_id=problem_id,
        input=input,
        expected_output=expected_output,
        is_sample=is_sample == "on",
        order_index=order_index,
    )
    db.add(tc)
    db.commit()
    return RedirectResponse(f"/admin/problems/{problem_id}/testcases", status_code=302)


@router.get("/testcases/{tc_id}/edit", response_class=HTMLResponse)
def edit_testcase_form(tc_id: int, request: Request, db: Session = Depends(get_db)):
    admin = get_admin_user(request, db)
    if not admin:
        return RedirectResponse("/login", status_code=302)
    tc = db.query(TestCase).filter(TestCase.id == tc_id).first()
    if not tc:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "admin/testcase_form.html", {
        "user": admin, "problem": tc.problem, "tc": tc
    })


@router.post("/testcases/{tc_id}/edit")
def update_testcase(
    tc_id: int,
    request: Request,
    input: str = Form(""),
    expected_output: str = Form(...),
    is_sample: Optional[str] = Form(None),
    order_index: int = Form(0),
    db: Session = Depends(get_db),
):
    admin = get_admin_user(request, db)
    if not admin:
        return RedirectResponse("/login", status_code=302)
    tc = db.query(TestCase).filter(TestCase.id == tc_id).first()
    if not tc:
        raise HTTPException(status_code=404)
    tc.input = input
    tc.expected_output = expected_output
    tc.is_sample = is_sample == "on"
    tc.order_index = order_index
    db.commit()
    return RedirectResponse(f"/admin/problems/{tc.problem_id}/testcases", status_code=302)


@router.post("/testcases/{tc_id}/delete")
def delete_testcase(tc_id: int, request: Request, db: Session = Depends(get_db)):
    admin = get_admin_user(request, db)
    if not admin:
        return RedirectResponse("/login", status_code=302)
    tc = db.query(TestCase).filter(TestCase.id == tc_id).first()
    if not tc:
        raise HTTPException(status_code=404)
    problem_id = tc.problem_id
    db.delete(tc)
    db.commit()
    return RedirectResponse(f"/admin/problems/{problem_id}/testcases", status_code=302)


# ── Users ─────────────────────────────────────────────────────────────────────

@router.get("/users", response_class=HTMLResponse)
def admin_users(request: Request, db: Session = Depends(get_db)):
    admin = get_admin_user(request, db)
    if not admin:
        return RedirectResponse("/login", status_code=302)
    users = db.query(User).order_by(User.created_at.desc()).all()
    return templates.TemplateResponse(request, "admin/users.html", {
        "user": admin, "users": users
    })


@router.post("/users/{user_id}/role")
def change_user_role(
    user_id: int,
    request: Request,
    role: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = get_admin_user(request, db)
    if not admin:
        return RedirectResponse("/login", status_code=302)
    target = db.query(User).filter(User.id == user_id).first()
    if not target or target.id == admin.id:
        return RedirectResponse("/admin/users", status_code=302)
    target.role = UserRole(role)
    db.commit()
    return RedirectResponse("/admin/users", status_code=302)


@router.post("/users/{user_id}/delete")
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    admin = get_admin_user(request, db)
    if not admin:
        return RedirectResponse("/login", status_code=302)
    target = db.query(User).filter(User.id == user_id).first()
    if not target or target.id == admin.id:
        return RedirectResponse("/admin/users", status_code=302)
    db.delete(target)
    db.commit()
    return RedirectResponse("/admin/users", status_code=302)
