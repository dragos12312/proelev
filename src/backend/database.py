# database setup, sqlalchemy 2 with sqlite
# the engine is created from DATABASE_URL env var, defaults to a local file
# tests override get_db with their own session that points to a temp file
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base


DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./proelev.db")

# check_same_thread is a sqlite quirk, fastapi uses different threads per request
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)


# sqlite doesnt enforce foreign keys by default, this turns them on for every connection
# without it the cascade delete on homework wont actually delete the children
@event.listens_for(engine, "connect")
def _enable_sqlite_fk(dbapi_conn, _):
    if DATABASE_URL.startswith("sqlite"):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
Base = declarative_base()


# fastapi dependency, opens a session per request and closes it at the end
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
