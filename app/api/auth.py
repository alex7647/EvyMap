from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..domain.fields import FIELDS
from ..domain.presets import PRESET_TYPES
from ..models import Organization, PlaceType, User
from ..schemas import LoginIn, RegisterIn, TokenOut, UserIn, UserOut
from ..security import OWNER, create_token, current_user, hash_password, verify_password

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "этот e-mail уже зарегистрирован")
    org = Organization(name=body.org_name)
    db.add(org)
    db.flush()
    user = User(org_id=org.id, email=email, password_hash=hash_password(body.password), role="owner")
    db.add(user)
    for preset in PRESET_TYPES:
        fields = [f.model_dump() for f in FIELDS.validate_python(preset["fields"])]
        db.add(PlaceType(org_id=org.id, **{**preset, "fields": fields}))
    db.commit()
    return TokenOut(access_token=create_token(user))


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "неверный e-mail или пароль")
    return TokenOut(access_token=create_token(user))


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_db), owner: User = Depends(OWNER)):
    """Владелец заводит редакторов и live-сотрудников (live_staff может только переносить активности)."""
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "этот e-mail уже зарегистрирован")
    user = User(org_id=owner.org_id, email=email, password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    db.commit()
    return user
