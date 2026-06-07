"""
Silver auth router.

Flow on login (3 factors, all required):
  POST /auth/login                 factor 1: email + password
                                   server creates a login_challenge row and
                                   mails the email code, returns challenge_id
  POST /auth/login/verify-email    factor 2: challenge_id + email_code
                                   server flips email_verified=1 and returns
                                   the user's security question to ask next
  POST /auth/login/verify-question factor 3: challenge_id + answer
                                   server checks against security_answer_hash,
                                   issues a token via issue_session_token

Other endpoints:
  POST /auth/register   creates a new USER row + security question
  POST /auth/logout     revokes the session jti
  POST /auth/forgot     creates a password_reset row, emails the token
  POST /auth/reset      consumes the token, sets the new bcrypt hash
  GET  /auth/me         caller info, used by frontend to validate cache
  GET  /auth/inbox      caller's mock inbox (admin sees all)
"""
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, Request, status
from sqlalchemy.orm import Session as DbSession

import login_throttle

from schemas import (
    LoginRequest, LoginResponse, RegisterRequest,
    LoginFactorOneResponse, LoginFactorTwoResponse,
    VerifyEmailRequest, VerifyQuestionRequest,
    ForgotRequest, ResetRequest,
)
from database import get_db
from models import (
    User, Role, LoginChallenge, PasswordReset, Session as UserSession,
    InviteCode, teacher_assignment, parent_child, SchoolClass, Subject,
    ROLE_USER, ROLE_ADMIN, ROLE_TEACHER, ROLE_STUDENT, ROLE_PARENT,
)
from routers.invites import consume_invite
from auth import (
    hash_password, verify_password,
    issue_session_token, decode_token, revoke_session,
    get_current_user,
)
from email_service import send as send_email, inbox_for, all_messages
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


router = APIRouter()
_bearer = HTTPBearer(auto_error=False)


def _safe_user(u: User) -> dict:
    """Build the user payload sent to the frontend.
    Always include id/email/name/role/permissions.
    For students attach `class`, for parents `children`, for teachers
    `assignments` = list of (class, subject) pairs they teach."""
    out = {
        "id":          u.id,
        "email":       u.email,
        "name":        u.name,
        "role":        u.role.name if u.role else None,
        "permissions": sorted(p.code for p in u.role.permissions) if u.role else [],
    }
    if u.school_class:
        out["class"] = {"id": u.school_class.id, "name": u.school_class.name}
    if u.children:
        out["children"] = [
            {"id": c.id, "email": c.email, "name": c.name,
             "class": {"id": c.school_class.id, "name": c.school_class.name} if c.school_class else None}
            for c in u.children
        ]
    # teacher: list of (class, subject) pairs they're assigned to
    from sqlalchemy.orm import object_session
    sess = object_session(u)
    if sess is not None:
        from sqlalchemy import select
        from models import teacher_assignment as _ta, SchoolClass as _SC, Subject as _SU
        rows = sess.execute(
            select(_ta.c.class_id, _ta.c.subject_id).where(_ta.c.user_id == u.id)
        ).all()
        if rows:
            pairs = []
            for cls_id, sub_id in rows:
                cl = sess.get(_SC, cls_id)
                su = sess.get(_SU, sub_id)
                pairs.append({
                    "class":   {"id": cl.id, "name": cl.name} if cl else None,
                    "subject": {"id": su.id, "name": su.name} if su else None,
                })
            out["assignments"] = pairs
    return out


def _now():
    return datetime.utcnow()


# ─── register ────────────────────────────────────────────────────────────────

@router.post("/register", response_model=LoginResponse, status_code=201)
def register(body: RegisterRequest, db: DbSession = Depends(get_db)):
    if db.query(User).filter_by(email=body.email).first():
        raise HTTPException(status_code=409, detail="Există deja un cont cu acest email")

    # ── resolve target role ───────────────────────────────────────────────
    # without an invite code the new account stays the legacy "user" role for
    # backward compat. with a code the code's role wins, and any preset class
    # or subject must be honored.
    invite: InviteCode | None = None
    target_role_name = ROLE_USER
    preset_class_id: int | None = None
    preset_subject_id: int | None = None
    if body.invite_code:
        inv = db.query(InviteCode).filter_by(code=body.invite_code.strip().upper()).first()
        if not inv:
            raise HTTPException(status_code=400, detail="Cod de invitație invalid")
        if inv.revoked:
            raise HTTPException(status_code=400, detail="Codul a fost revocat")
        if inv.used_by_user_id:
            raise HTTPException(status_code=400, detail="Codul a fost deja folosit")
        if inv.expires_at < _now():
            raise HTTPException(status_code=400, detail="Codul a expirat")
        invite = inv
        target_role_name  = inv.role_name
        preset_class_id   = inv.class_id
        preset_subject_id = inv.subject_id

    target_role = db.query(Role).filter_by(name=target_role_name).first()
    if not target_role:
        raise HTTPException(status_code=500, detail=f"Rolul {target_role_name} lipsește din baza de date")

    # ── role-specific input validation ───────────────────────────────────
    if target_role_name == ROLE_STUDENT:
        cls_id = preset_class_id or body.class_id
        if not cls_id:
            raise HTTPException(status_code=400, detail="Elevii trebuie să aibă o clasă")
        if not db.get(SchoolClass, cls_id):
            raise HTTPException(status_code=400, detail="Clasa nu există")
    elif target_role_name == ROLE_TEACHER:
        cls_id = preset_class_id or body.class_id
        sub_id = preset_subject_id or body.subject_id
        if not cls_id or not sub_id:
            raise HTTPException(status_code=400, detail="Profesorii trebuie să aibă o clasă și o materie")
        if not db.get(SchoolClass, cls_id):
            raise HTTPException(status_code=400, detail="Clasa nu există")
        if not db.get(Subject, sub_id):
            raise HTTPException(status_code=400, detail="Materia nu există")
    elif target_role_name == ROLE_PARENT:
        emails = [e.strip().lower() for e in (body.children_emails or []) if e and e.strip()]
        if not emails:
            raise HTTPException(status_code=400, detail="Părinții trebuie să aibă cel puțin un copil")
        # all child emails must point at existing student users
        children = db.query(User).filter(User.email.in_(emails)).all()
        if len(children) != len(emails):
            missing = set(emails) - {c.email for c in children}
            raise HTTPException(status_code=400, detail=f"Nu am găsit conturi pentru: {', '.join(sorted(missing))}")
        non_students = [c.email for c in children if not c.role or c.role.name != ROLE_STUDENT]
        if non_students:
            raise HTTPException(status_code=400, detail=f"Aceste conturi nu sunt elevi: {', '.join(non_students)}")

    # ── create the row ───────────────────────────────────────────────────
    user = User(
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
        role_id=target_role.id,
        security_question=body.security_question,
        security_answer_hash=hash_password(body.security_answer.strip().lower()),
        class_id=(preset_class_id or body.class_id) if target_role_name == ROLE_STUDENT else None,
    )
    db.add(user)
    db.flush()

    # ── wire up role-specific relations ──────────────────────────────────
    if target_role_name == ROLE_TEACHER:
        cls_id = preset_class_id or body.class_id
        sub_id = preset_subject_id or body.subject_id
        db.execute(teacher_assignment.insert().values(
            user_id=user.id, class_id=cls_id, subject_id=sub_id,
        ))
    elif target_role_name == ROLE_PARENT:
        emails = [e.strip().lower() for e in (body.children_emails or [])]
        children = db.query(User).filter(User.email.in_(emails)).all()
        for ch in children:
            db.execute(parent_child.insert().values(
                parent_user_id=user.id, child_user_id=ch.id,
            ))

    # ── consume the invite ──────────────────────────────────────────────
    if invite is not None:
        invite.used_by_user_id = user.id
        invite.used_at = _now()

    db.commit()
    db.refresh(user)

    # registration auto-logs the user in, single token, no need for the
    # 3 factor wizard since they JUST set everything up
    token = issue_session_token(db, user)
    return LoginResponse(
        message="Cont creat",
        user=_safe_user(user),
        access_token=token,
    )


# ─── login factor 1, password ───────────────────────────────────────────────

def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


@router.post("/login", response_model=LoginFactorOneResponse)
def login_factor_one(body: LoginRequest, request: Request, db: DbSession = Depends(get_db)):
    ip = _client_ip(request)

    # gold defense, refuse the request entirely if this (ip, email) pair
    # has been hammering us with bad passwords
    locked, retry_in = login_throttle.is_locked(ip, body.email)
    if locked:
        raise HTTPException(
            status_code=429,
            detail=f"Prea multe încercări eșuate, încearcă din nou peste {retry_in}s",
            headers={"Retry-After": str(retry_in)},
        )

    user = db.query(User).filter_by(email=body.email.strip().lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        newly_locked, _retry = login_throttle.record_failure(ip, body.email)
        raise HTTPException(
            status_code=429 if newly_locked else 401,
            detail="Email sau parolă incorecte",
        )

    # password matched, clear the bad-attempt counter for the next login
    login_throttle.record_success(ip, body.email)

    # mint a challenge, write the row, send the email code
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge_id = secrets.token_urlsafe(24)
    now = _now()
    db.add(LoginChallenge(
        user_id=user.id,
        challenge_id=challenge_id,
        email_code=code,
        email_verified=0,
        completed=0,
        created_at=now,
        expires_at=now + timedelta(minutes=10),
    ))
    db.commit()
    send_email(
        to=user.email,
        subject="Codul tău de autentificare ProElev",
        body=f"Salut {user.name},\n\nCodul de autentificare este {code}. "
             "Acesta expiră în 10 minute.\n\nDacă nu ai inițiat această "
             "cerere, ignor-o.",
        code=code,
    )
    return LoginFactorOneResponse(
        message="Verifică inbox-ul pentru codul de autentificare",
        challenge_id=challenge_id,
    )


def _load_challenge(db: DbSession, challenge_id: str) -> LoginChallenge:
    ch = db.query(LoginChallenge).filter_by(challenge_id=challenge_id).first()
    if not ch:
        raise HTTPException(status_code=400, detail="Provocare invalidă")
    if ch.expires_at < _now() or ch.completed:
        raise HTTPException(status_code=400, detail="Provocarea a expirat")
    return ch


# ─── login factor 2, email code ─────────────────────────────────────────────

@router.post("/login/verify-email", response_model=LoginFactorTwoResponse)
def verify_email(body: VerifyEmailRequest, db: DbSession = Depends(get_db)):
    ch = _load_challenge(db, body.challenge_id)
    if body.code.strip() != ch.email_code:
        raise HTTPException(status_code=400, detail="Cod incorect")

    ch.email_verified = 1
    db.commit()

    user = db.get(User, ch.user_id)
    # if the user has no security question recorded (legacy admin etc.) we
    # still require something the third step uses a stock fallback question
    question = user.security_question or "Care este parola ta de la pasul 1?"
    return LoginFactorTwoResponse(
        message="Email verificat",
        challenge_id=ch.challenge_id,
        security_question=question,
    )


# ─── login factor 3, security question ─────────────────────────────────────

@router.post("/login/verify-question", response_model=LoginResponse)
def verify_question(body: VerifyQuestionRequest, db: DbSession = Depends(get_db)):
    ch = _load_challenge(db, body.challenge_id)
    if not ch.email_verified:
        raise HTTPException(status_code=400, detail="Trebuie să verifici emailul mai întâi")

    user = db.get(User, ch.user_id)

    # legacy users without a question saved fall back to verifying the password
    # again, so the existing seeded admin still has 3 factors total
    answer = body.answer.strip().lower()
    if user.security_answer_hash:
        if not verify_password(answer, user.security_answer_hash):
            raise HTTPException(status_code=400, detail="Răspuns incorect")
    else:
        if not verify_password(body.answer, user.password_hash):
            raise HTTPException(status_code=400, detail="Răspuns incorect")

    # all three factors satisfied, finalize the challenge and mint a token
    ch.completed = 1
    db.commit()
    token = issue_session_token(db, user)
    return LoginResponse(
        message="Autentificare reușită",
        user=_safe_user(user),
        access_token=token,
    )


# ─── me ─────────────────────────────────────────────────────────────────────

@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _safe_user(user)


# ─── logout, revokes the current session ────────────────────────────────────

@router.post("/logout")
def logout(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    db: DbSession = Depends(get_db),
):
    if not creds:
        return {"ok": True}  # nothing to revoke
    try:
        payload = decode_token(creds.credentials)
        jti = payload.get("jti")
        if jti:
            revoke_session(db, jti)
    except Exception:
        pass
    return {"ok": True}


# ─── password recovery ─────────────────────────────────────────────────────

@router.post("/forgot")
def forgot_password(body: ForgotRequest, db: DbSession = Depends(get_db)):
    # always return 200 so an attacker cant probe which emails exist
    user = db.query(User).filter_by(email=body.email.strip().lower()).first()
    if user:
        token = secrets.token_urlsafe(32)
        now = _now()
        db.add(PasswordReset(
            user_id=user.id, token=token,
            expires_at=now + timedelta(minutes=30),
            used=0, created_at=now,
        ))
        db.commit()
        send_email(
            to=user.email,
            subject="Resetare parolă ProElev",
            body=f"Salut {user.name},\n\nFolosește codul de mai jos pentru a-ți reseta parola "
                 f"în pagina de recuperare. Codul expiră în 30 de minute.",
            code=token,
        )
    return {"message": "Dacă există un cont cu acest email, am trimis instrucțiunile de resetare"}


@router.post("/reset")
def reset_password(body: ResetRequest, db: DbSession = Depends(get_db)):
    pr = db.query(PasswordReset).filter_by(token=body.token).first()
    if not pr or pr.used or pr.expires_at < _now():
        raise HTTPException(status_code=400, detail="Codul de resetare este invalid sau a expirat")

    user = db.get(User, pr.user_id)
    if not user:
        raise HTTPException(status_code=400, detail="Cont inexistent")

    user.password_hash = hash_password(body.new_password)
    pr.used = 1
    # bonus, also revoke every existing session so the attacker (if any) is kicked
    db.query(UserSession).filter_by(user_id=user.id, revoked=0).update({"revoked": 1})
    db.commit()
    return {"message": "Parolă schimbată"}


# ─── mock inbox ────────────────────────────────────────────────────────────

@router.get("/inbox")
def my_inbox(user: User = Depends(get_current_user)):
    """Caller's own mock inbox. Admins see everyone's mail because the lab
    teacher will want to verify the codes that get sent during the demo."""
    if user.role and user.role.name == ROLE_ADMIN:
        return all_messages()
    return inbox_for(user.email)


@router.get("/inbox/last")
def my_last_email(to: str, db: DbSession = Depends(get_db)):
    """Convenience endpoint, anyone can pull the most recent message for a
    given address from the mock inbox. Lets unauthenticated flows like login
    or recovery look up the code without needing to log in first.
    Real email would never expose this, but the mock inbox is local-only."""
    items = inbox_for(to)
    if not items:
        raise HTTPException(status_code=404, detail="Inbox gol")
    return items[0]
