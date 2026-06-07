"""
Public lookup endpoints used by the register form before the user has any
auth token. Returns the list of classes and subjects so the form can render
dropdowns when the invite code didn't preset a class or subject.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import SchoolClass, Subject


router = APIRouter()


@router.get("/classes")
def list_classes(db: Session = Depends(get_db)):
    return [{"id": c.id, "name": c.name} for c in db.query(SchoolClass).order_by(SchoolClass.name).all()]


@router.get("/subjects")
def list_subjects(db: Session = Depends(get_db)):
    return [{"id": s.id, "name": s.name} for s in db.query(Subject).order_by(Subject.name).all()]
