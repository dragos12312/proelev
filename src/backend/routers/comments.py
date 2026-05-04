# comments endpoints, a homework has many comments so urls are nested under the homework
# same shape as the students router on purpose, easier to remember
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session

from schemas import (
    CommentCreate, CommentUpdate,
    CommentResponse, PaginatedComments, CommentStatistics,
)
from database import get_db
from models import Homework, Comment
from serialize import comment_to_dict

router = APIRouter()


# 404 if the parent homework doesnt exist, same pattern as in students
def _require_homework(db: Session, hw_id: int) -> Homework:
    hw = db.get(Homework, hw_id)
    if not hw:
        raise HTTPException(status_code=404, detail=f"Tema cu id={hw_id} nu a fost găsită")
    return hw


def _find_comment(db: Session, hw_id: int, comment_id: int) -> Comment:
    c = db.query(Comment).filter_by(id=comment_id, homework_id=hw_id).first()
    if not c:
        raise HTTPException(
            status_code=404,
            detail=f"Comentariul cu id={comment_id} nu a fost găsit pentru tema {hw_id}"
        )
    return c


# server decides the createdAt so the client cant fake it
@router.post("/{hw_id}/comments", response_model=CommentResponse, status_code=201)
def add_comment(hw_id: int, body: CommentCreate, db: Session = Depends(get_db)):
    _require_homework(db, hw_id)
    c = Comment(
        homework_id=hw_id,
        author=body.author,
        text=body.text,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return comment_to_dict(c)


@router.get("/{hw_id}/comments", response_model=PaginatedComments)
def list_comments(
    hw_id:    int,
    page:     int = Query(default=1,  ge=1),
    pageSize: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    _require_homework(db, hw_id)
    q = db.query(Comment).filter_by(homework_id=hw_id)
    total = q.count()
    totalPages = max(1, -(-total // pageSize))
    items = q.order_by(Comment.id).offset((page - 1) * pageSize).limit(pageSize).all()

    return PaginatedComments(
        items=[CommentResponse(**comment_to_dict(c)) for c in items],
        total=total,
        page=page,
        pageSize=pageSize,
        totalPages=totalPages,
    )


# small stats bundle, how many comments, how many unique authors, who posts the most
@router.get("/{hw_id}/comments/statistics", response_model=CommentStatistics)
def comment_statistics(hw_id: int, db: Session = Depends(get_db)):
    _require_homework(db, hw_id)
    items = db.query(Comment).filter_by(homework_id=hw_id).all()
    authors = [c.author for c in items]
    author_counts: dict[str, int] = {}
    for a in authors:
        author_counts[a] = author_counts.get(a, 0) + 1
    top_author = max(author_counts, key=author_counts.get) if author_counts else None
    avg_len = (sum(len(c.text) for c in items) / len(items)) if items else 0.0

    return CommentStatistics(
        homeworkId=hw_id,
        totalComments=len(items),
        uniqueAuthors=len(set(authors)),
        averageTextLength=round(avg_len, 2),
        topAuthor=top_author,
    )


@router.get("/{hw_id}/comments/{comment_id}", response_model=CommentResponse)
def get_comment(hw_id: int, comment_id: int, db: Session = Depends(get_db)):
    _require_homework(db, hw_id)
    return comment_to_dict(_find_comment(db, hw_id, comment_id))


@router.put("/{hw_id}/comments/{comment_id}", response_model=CommentResponse)
def update_comment(hw_id: int, comment_id: int, body: CommentUpdate, db: Session = Depends(get_db)):
    _require_homework(db, hw_id)
    c = _find_comment(db, hw_id, comment_id)
    data = body.model_dump(exclude_unset=True)
    if "author" in data: c.author = data["author"]
    if "text"   in data: c.text   = data["text"]
    db.commit()
    db.refresh(c)
    return comment_to_dict(c)


@router.delete("/{hw_id}/comments/{comment_id}", status_code=204)
def delete_comment(hw_id: int, comment_id: int, db: Session = Depends(get_db)):
    _require_homework(db, hw_id)
    c = _find_comment(db, hw_id, comment_id)
    db.delete(c)
    db.commit()
