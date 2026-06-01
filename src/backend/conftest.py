# pytest fixtures, swap the real db for a fresh in memory sqlite per test session
# this way the existing 107 tests keep working but they hit a real db now
import os
import tempfile

# point DATABASE_URL, CHAT_DB_PATH and EMAIL_DB_PATH at a temp folder
# BEFORE the apps import them
_tmp_dir = tempfile.mkdtemp(prefix="proelev_tests_")
_db_path = os.path.join(_tmp_dir, "test.db")
os.environ["DATABASE_URL"]   = f"sqlite:///{_db_path}"
os.environ["CHAT_DB_PATH"]   = os.path.join(_tmp_dir, "chat.json")
os.environ["EMAIL_DB_PATH"]  = os.path.join(_tmp_dir, "email.json")

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


# gold, defense middleware keeps in-memory rate-limit buckets and a login
# throttle, both need to be cleared between tests or one test's traffic
# poisons the next. an autouse fixture handles that for every test file.
import pytest  # noqa: E402
import defense_middleware  # noqa: E402
import login_throttle  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_defense_state():
    defense_middleware.reset_for_tests()
    login_throttle.reset_for_tests()
    yield
