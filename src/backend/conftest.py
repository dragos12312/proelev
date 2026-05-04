# pytest fixtures, swap the real db for a fresh in memory sqlite per test session
# this way the existing 107 tests keep working but they hit a real db now
import os
import tempfile

# point DATABASE_URL and CHAT_DB_PATH at a temp folder BEFORE the apps import them
_tmp_dir = tempfile.mkdtemp(prefix="proelev_tests_")
_db_path = os.path.join(_tmp_dir, "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["CHAT_DB_PATH"] = os.path.join(_tmp_dir, "chat.json")

# now we can safely import the app and friends
from database import Base, engine, SessionLocal  # noqa: E402
import models  # noqa: F401, E402  registers all models on Base

# create the schema directly from sqlalchemy metadata, this is the same shape
# alembic would produce, the migration smoke test in test_db.py confirms that
Base.metadata.create_all(bind=engine)

# seed the lookup tables and the default admin once, every test starts from here
from seed import seed_lookups  # noqa: E402

_db = SessionLocal()
try:
    seed_lookups(_db)
finally:
    _db.close()
