# login endpoint, just checks email and password against the user table
# response also carries the role name and the list of permission codes
# the frontend uses to hide admin only buttons
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from schemas import LoginRequest, LoginResponse
from database import get_db
from models import User

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    # find the first user whose email and password both match
    user = db.query(User).filter_by(email=body.email, password=body.password).first()
    if not user:
        raise HTTPException(status_code=401, detail="Email sau parolă incorecte")

    # never send the password back to the client
    # role name and permission codes drive the role gating in the ui
    safe_user = {
        "id":          user.id,
        "email":       user.email,
        "name":        user.name,
        "role":        user.role.name if user.role else None,
        "permissions": sorted(p.code for p in user.role.permissions) if user.role else [],
    }
    return LoginResponse(message="Autentificare reușită", user=safe_user)
