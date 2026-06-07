# helpers that flatten an orm row into the dict shape the api returns
# the api still talks subject/assignedClass as plain strings so the frontend doesnt change
# but in the db those are foreign keys to the subject and school_class lookup tables
from sqlalchemy.orm import Session

from models import Homework, Student, Comment, Subject, SchoolClass


# turn a homework orm row into the response dict
# we lazy load subject and assigned_class through the relationships
def homework_to_dict(hw: Homework) -> dict:
    return {
        "id":            hw.id,
        "title":         hw.title,
        "subject":       hw.subject.name if hw.subject else None,
        "assignedClass": hw.assigned_class.name if hw.assigned_class else None,
        "dueDate":       hw.due_date.isoformat() if hw.due_date else None,
        "description":   hw.description,
        "fileName":      hw.file_name,
    }


def student_to_dict(s: Student) -> dict:
    return {
        "id":             s.id,
        "homeworkId":     s.homework_id,
        "userId":         s.user_id,
        "name":           s.name,
        "dateTime":       s.date_time,
        "grade":          s.grade,
        # assignment 6 submission + feedback
        "submittedAt":         s.submitted_at.isoformat() + "Z" if s.submitted_at else None,
        "submissionText":      s.submission_text,
        "submissionFileName":  s.submission_file_name,
        "hasFile":             bool(s.submission_blob),
        "feedback":            s.feedback,
    }


def comment_to_dict(c: Comment) -> dict:
    return {
        "id":         c.id,
        "homeworkId": c.homework_id,
        "author":     c.author,
        "text":       c.text,
        "createdAt":  c.created_at,
    }


# look up a subject row by its name, raises KeyError if it doesnt exist
def subject_by_name(db: Session, name: str) -> Subject:
    s = db.query(Subject).filter_by(name=name).first()
    if not s:
        raise KeyError(name)
    return s


def class_by_name(db: Session, name: str) -> SchoolClass:
    c = db.query(SchoolClass).filter_by(name=name).first()
    if not c:
        raise KeyError(name)
    return c
