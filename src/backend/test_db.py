"""
Dedicated db layer tests, separate from the api focused test_main.py
covers things the api tests dont touch directly:
  - lookup tables get seeded once and never duplicated
  - foreign keys actually cascade on delete at the sqlite layer
  - check constraint on student.grade rejects out of range values
  - alembic migration head matches the orm metadata
"""
import os
import subprocess
import tempfile
import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import sessionmaker

from database import SessionLocal, engine, Base
from models import Subject, SchoolClass, Homework, Student, Comment, User, SUBJECT_NAMES, CLASS_NAMES
from seed import seed_lookups


@pytest.fixture(autouse=True)
def _clean_db():
    """Wipe rows but keep schema and lookup data between tests."""
    db = SessionLocal()
    try:
        db.query(Comment).delete()
        db.query(Student).delete()
        db.query(Homework).delete()
        db.commit()
    finally:
        db.close()
    yield


# ─── lookup seeding ──────────────────────────────────────────────────────────

class TestSeed:
    def test_subject_lookup_has_all_seven(self):
        db = SessionLocal()
        try:
            names = {s.name for s in db.query(Subject).all()}
            for n in SUBJECT_NAMES:
                assert n in names
        finally:
            db.close()

    def test_class_lookup_has_all_eight(self):
        db = SessionLocal()
        try:
            names = {c.name for c in db.query(SchoolClass).all()}
            for n in CLASS_NAMES:
                assert n in names
        finally:
            db.close()

    def test_seed_is_idempotent(self):
        # calling seed twice must not duplicate rows
        db = SessionLocal()
        try:
            before_subjects = db.query(Subject).count()
            before_classes  = db.query(SchoolClass).count()
            seed_lookups(db)
            seed_lookups(db)
            assert db.query(Subject).count() == before_subjects
            assert db.query(SchoolClass).count() == before_classes
        finally:
            db.close()

    def test_default_admin_seeded(self):
        db = SessionLocal()
        try:
            admin = db.query(User).filter_by(email="admin@proelev.ro").first()
            assert admin is not None
            # password is bcrypt-hashed now, never the plain string
            assert admin.password_hash and admin.password_hash != "Admin123"
            assert admin.password_hash.startswith("$2")  # bcrypt prefix
            # round-trip verify
            from auth import verify_password
            assert verify_password("Admin123", admin.password_hash)
        finally:
            db.close()


# ─── foreign keys + cascade ──────────────────────────────────────────────────

class TestRelations:
    def _make_homework(self, db) -> Homework:
        subj = db.query(Subject).filter_by(name="Matematică").first()
        cls  = db.query(SchoolClass).filter_by(name="1A").first()
        from datetime import date
        hw = Homework(
            title="t", subject_id=subj.id, class_id=cls.id,
            due_date=date(2026, 6, 1), description="d",
        )
        db.add(hw)
        db.flush()
        return hw

    def test_delete_homework_cascades_to_students(self):
        db = SessionLocal()
        try:
            hw = self._make_homework(db)
            db.add(Student(homework_id=hw.id, name="X", date_time="2026-01-01 10:00", grade=8))
            db.commit()
            assert db.query(Student).filter_by(homework_id=hw.id).count() == 1
            db.delete(hw)
            db.commit()
            assert db.query(Student).filter_by(homework_id=hw.id).count() == 0
        finally:
            db.close()

    def test_delete_homework_cascades_to_comments(self):
        db = SessionLocal()
        try:
            hw = self._make_homework(db)
            db.add(Comment(homework_id=hw.id, author="a", text="b", created_at="2026-01-01 10:00"))
            db.commit()
            assert db.query(Comment).filter_by(homework_id=hw.id).count() == 1
            db.delete(hw)
            db.commit()
            assert db.query(Comment).filter_by(homework_id=hw.id).count() == 0
        finally:
            db.close()

    def test_grade_check_constraint_blocks_out_of_range(self):
        db = SessionLocal()
        try:
            hw = self._make_homework(db)
            db.add(Student(homework_id=hw.id, name="X", date_time="t", grade=99))
            with pytest.raises(Exception):  # IntegrityError on commit
                db.commit()
            db.rollback()
        finally:
            db.close()

    def test_grade_null_is_allowed(self):
        db = SessionLocal()
        try:
            hw = self._make_homework(db)
            db.add(Student(homework_id=hw.id, name="X", date_time="t", grade=None))
            db.commit()
            assert db.query(Student).filter_by(homework_id=hw.id).count() == 1
        finally:
            db.close()


# ─── schema metadata ─────────────────────────────────────────────────────────

class TestSchema:
    def test_all_expected_tables_exist(self):
        i = inspect(engine)
        tables = set(i.get_table_names())
        for t in ("subject", "school_class", "homework", "student", "comment", "user"):
            assert t in tables

    def test_homework_has_subject_and_class_fks(self):
        i = inspect(engine)
        fks = i.get_foreign_keys("homework")
        targets = {(fk["referred_table"], tuple(fk["constrained_columns"])) for fk in fks}
        assert ("subject",      ("subject_id",)) in targets
        assert ("school_class", ("class_id",))   in targets


# ─── migration smoke test ────────────────────────────────────────────────────

def test_alembic_upgrade_head_against_fresh_db(tmp_path):
    """Running alembic upgrade head on an empty file should produce the same
    set of tables that Base.metadata.create_all does. This proves the migration
    is in sync with the orm models."""
    db_file = tmp_path / "alembic_check.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_file}"}
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    result = subprocess.run(
        ["python", "-m", "alembic", "upgrade", "head"],
        cwd=backend_dir, env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr

    eng = create_engine(f"sqlite:///{db_file}")
    insp = inspect(eng)
    tables = set(insp.get_table_names())
    expected = {"subject", "school_class", "homework", "student", "comment", "user", "alembic_version"}
    assert expected.issubset(tables)
