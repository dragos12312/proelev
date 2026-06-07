"""
Assignment 6, role-aware helpers used by the homework + submission routers.

The point is a single place that maps "current user" -> the set of homeworks
they're allowed to read or grade, so individual routes stay clean.

Rules summary:
  admin / user      -> see everything
  teacher           -> homeworks whose (class, subject) match one of their
                       teacher_assignment rows. + anything they created.
  student           -> homeworks for their own class
  parent            -> homeworks for any of their children's classes
"""
from typing import Iterable
from sqlalchemy import or_, and_, select
from sqlalchemy.orm import Session

from models import (
    Homework, User, teacher_assignment, parent_child,
    ROLE_ADMIN, ROLE_USER, ROLE_TEACHER, ROLE_STUDENT, ROLE_PARENT,
)


def homework_visible_filter(db: Session, user: User):
    """Return a SQLAlchemy filter expression that, when applied to a
    Homework query, limits results to ones the caller can see."""
    role = user.role.name if user.role else None

    if role in (ROLE_ADMIN, ROLE_USER, None):
        # legacy + admin see all
        return None  # caller should skip applying any filter

    if role == ROLE_TEACHER:
        # subquery of (class_id, subject_id) pairs they teach
        pairs = (
            select(teacher_assignment.c.class_id, teacher_assignment.c.subject_id)
            .where(teacher_assignment.c.user_id == user.id)
        ).subquery()
        return or_(
            Homework.created_by_user_id == user.id,
            and_(
                Homework.class_id   == pairs.c.class_id,
                Homework.subject_id == pairs.c.subject_id,
            ),
        )

    if role == ROLE_STUDENT:
        if user.class_id is None:
            # student without a class shouldn't see anything
            return Homework.id == -1
        return Homework.class_id == user.class_id

    if role == ROLE_PARENT:
        # collect the children's class_ids
        child_class_ids = [c.class_id for c in user.children if c.class_id]
        if not child_class_ids:
            return Homework.id == -1
        return Homework.class_id.in_(child_class_ids)

    # any other role gets nothing by default
    return Homework.id == -1


def can_see_homework(db: Session, user: User, hw: Homework) -> bool:
    """Cheap in-Python check, useful for single-resource endpoints."""
    role = user.role.name if user.role else None
    if role in (ROLE_ADMIN, ROLE_USER, None):
        return True
    if role == ROLE_TEACHER:
        if hw.created_by_user_id == user.id:
            return True
        rows = db.execute(
            select(teacher_assignment.c.user_id).where(
                teacher_assignment.c.user_id    == user.id,
                teacher_assignment.c.class_id   == hw.class_id,
                teacher_assignment.c.subject_id == hw.subject_id,
            )
        ).first()
        return rows is not None
    if role == ROLE_STUDENT:
        return hw.class_id == user.class_id
    if role == ROLE_PARENT:
        child_class_ids = {c.class_id for c in user.children if c.class_id}
        return hw.class_id in child_class_ids
    return False


def can_grade_homework(db: Session, user: User, hw: Homework) -> bool:
    """Admin grades anything; teacher grades only their own homeworks."""
    role = user.role.name if user.role else None
    if role == ROLE_ADMIN:
        return True
    if role == ROLE_TEACHER:
        return hw.created_by_user_id == user.id
    return False


def can_post_homework(db: Session, user: User, class_id: int, subject_id: int) -> bool:
    """Who can POST /homeworks for a given (class, subject)."""
    role = user.role.name if user.role else None
    if role == ROLE_ADMIN:
        return True
    if role == ROLE_TEACHER:
        rows = db.execute(
            select(teacher_assignment.c.user_id).where(
                teacher_assignment.c.user_id    == user.id,
                teacher_assignment.c.class_id   == class_id,
                teacher_assignment.c.subject_id == subject_id,
            )
        ).first()
        return rows is not None
    return False
