"""
Heavy seeder for the assignment 5 gold demo.

Creates enough fake data that the naive M2M aggregation query in
/stats/by-tag becomes visibly slow without indices or caching.

Default sizes (override with env vars):
    SEED_HOMEWORKS   30
    SEED_STUDENTS_PER_HW 200       so ~6000 student rows per hw, total ~6000
    SEED_TAGS        30
    SEED_TAG_LINKS_AVG 4           each student carries ~4 tags

Idempotent: skips if the heavy seed has already run (detected by checking
that the tag table already has rows).

Run from the backend folder:
    python scripts/seed_heavy.py
or as a module:
    python -m scripts.seed_heavy
"""
import os
import random
import sys
import time
from datetime import datetime, timedelta, date
from pathlib import Path

# this script lives in src/backend/scripts/, the backend modules are one level up
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from faker import Faker
from sqlalchemy.orm import Session as DbSession

from database import SessionLocal
from models import (
    Homework, Student, Tag, Subject, SchoolClass, student_tag,
)


SEED_HOMEWORKS       = int(os.environ.get("SEED_HOMEWORKS",        "30"))
SEED_STUDENTS_PER_HW = int(os.environ.get("SEED_STUDENTS_PER_HW", "200"))
SEED_TAGS            = int(os.environ.get("SEED_TAGS",             "30"))
SEED_TAG_LINKS_AVG   = int(os.environ.get("SEED_TAG_LINKS_AVG",     "4"))


def main() -> None:
    fake = Faker("ro_RO")
    Faker.seed(42)
    random.seed(42)

    db: DbSession = SessionLocal()
    try:
        # idempotency guard
        if db.query(Tag).count() > 0:
            print("[seed_heavy] tags already present, skipping")
            return

        subjects = db.query(Subject).all()
        classes  = db.query(SchoolClass).all()
        if not subjects or not classes:
            print("[seed_heavy] lookup tables empty, run normal seed first")
            return

        # ── tags ────────────────────────────────────────────────────────────
        tag_words = [
            "olimpic", "restantier", "bursier", "lider_clasă", "creativ",
            "atent", "linistit", "vorbăreț", "intârzie", "fără_temă",
            "exemplar", "premiat", "concurs", "lectură", "sport",
            "matematică_avansată", "limbi_străine", "tehnic", "artistic",
            "social", "voluntariat", "ajutor", "responsabil", "punctual",
            "implicat", "distras", "obraznic", "modest", "ambiitios", "harnic",
        ]
        random.shuffle(tag_words)
        tags = [Tag(name=w) for w in tag_words[:SEED_TAGS]]
        db.add_all(tags)
        db.flush()
        print(f"[seed_heavy] created {len(tags)} tags")

        # ── homeworks ──────────────────────────────────────────────────────
        homeworks = []
        for i in range(SEED_HOMEWORKS):
            hw = Homework(
                title=fake.sentence(nb_words=4).rstrip("."),
                subject_id=random.choice(subjects).id,
                class_id=random.choice(classes).id,
                due_date=date.today() + timedelta(days=random.randint(-30, 30)),
                description=fake.paragraph(nb_sentences=1),
                file_name=None,
            )
            db.add(hw)
            homeworks.append(hw)
        db.flush()
        print(f"[seed_heavy] created {len(homeworks)} homeworks")

        # ── student rows + tag links, bulk inserted for speed ──────────────
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        student_rows = []
        for hw in homeworks:
            for _ in range(SEED_STUDENTS_PER_HW):
                grade = random.choice([None, *range(1, 11)])
                student_rows.append({
                    "homework_id": hw.id,
                    "name":        fake.name(),
                    "date_time":   now_str,
                    "grade":       grade,
                })
        # bulk insert students
        db.bulk_insert_mappings(Student, student_rows)
        db.flush()
        total_students = db.query(Student).count()
        print(f"[seed_heavy] inserted {total_students} students")

        # ── tag links ──────────────────────────────────────────────────────
        # build a list of (student_id, tag_id) pairs and bulk insert
        all_student_ids = [s_id for (s_id,) in db.query(Student.id).all()]
        tag_ids         = [t.id for t in tags]

        seen = set()
        link_rows = []
        for sid in all_student_ids:
            k = max(1, int(random.gauss(SEED_TAG_LINKS_AVG, 1.5)))
            picks = random.sample(tag_ids, min(k, len(tag_ids)))
            for tid in picks:
                if (sid, tid) in seen:
                    continue
                seen.add((sid, tid))
                link_rows.append({"student_id": sid, "tag_id": tid})
        # bulk insert into the M2M
        db.execute(student_tag.insert(), link_rows)
        db.commit()
        print(f"[seed_heavy] inserted {len(link_rows)} student_tag rows")
        print("[seed_heavy] done")
    finally:
        db.close()


if __name__ == "__main__":
    t = time.time()
    main()
    print(f"[seed_heavy] elapsed {time.time() - t:.1f}s")
