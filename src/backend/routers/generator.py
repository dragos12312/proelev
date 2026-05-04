# bronze challenge, backgroud thread that spits out fake homeworks every few seconds
# used to prove that the websocket updates and the infinite scroll actually work with live data
import asyncio
import random
from datetime import date, timedelta
from fastapi import APIRouter
from faker import Faker

from database import SessionLocal
from models import Homework, Student, Subject, SchoolClass, SUBJECT_NAMES, CLASS_NAMES
from serialize import homework_to_dict

router = APIRouter()
# ro_RO locale so the fake names look romanian
fake = Faker('ro_RO')

_task: asyncio.Task | None = None
_running = False


# makes one fake homework and between 3 and 6 fake students for it
# writes through sqlalchemy so it ends up in the same db as the real endpoints
def _generate_batch() -> dict:
    db = SessionLocal()
    try:
        subj_name = random.choice(SUBJECT_NAMES)
        cls_name  = random.choice(CLASS_NAMES)
        subj = db.query(Subject).filter_by(name=subj_name).first()
        cls  = db.query(SchoolClass).filter_by(name=cls_name).first()
        if not subj or not cls:
            return {}

        hw = Homework(
            title=fake.sentence(nb_words=4).rstrip('.'),
            subject_id=subj.id,
            class_id=cls.id,
            due_date=date.today() + timedelta(days=random.randint(0, 30)),
            description=fake.paragraph(nb_sentences=2),
            file_name=None,
        )
        db.add(hw)
        db.flush()

        for _ in range(random.randint(3, 6)):
            db.add(Student(
                homework_id=hw.id,
                name=fake.name(),
                date_time=fake.date_time_this_year().strftime("%Y-%m-%d %H:%M"),
                grade=random.choice([None, None, *range(1, 11)]),
            ))
        db.commit()
        db.refresh(hw)
        return homework_to_dict(hw)
    finally:
        db.close()


# keeps running untill someone calls stop, every 5 seconds it makes a new batch
async def _generator_loop():
    global _running
    _running = True
    while _running:
        hw = _generate_batch()
        # importing broadcast here instead of at the top to avoid a circular import
        from main import broadcast
        await broadcast({"event": "new_batch", "homework": hw})
        await asyncio.sleep(5)


@router.post("/start")
async def start_generator():
    global _task, _running
    if _task and not _task.done():
        return {"status": "already running"}
    _running = True
    _task = asyncio.create_task(_generator_loop())
    return {"status": "started"}


@router.post("/stop")
async def stop_generator():
    global _task, _running
    _running = False
    if _task:
        _task.cancel()
        _task = None
    return {"status": "stopped"}


@router.get("/status")
async def generator_status():
    return {"running": _running and _task is not None and not _task.done()}
