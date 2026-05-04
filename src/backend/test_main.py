"""
run with pytest test_main.py -v
"""
import asyncio
import pytest
from fastapi.testclient import TestClient

# conftest.py points DATABASE_URL at a temp sqlite and creates the schema
# from here on we just talk to the orm through the same SessionLocal the app uses
from database import SessionLocal
from models import Homework, Student, Comment, User
from seed import seed_lookups

from main import app

client = TestClient(app)


def _reset_db():
    """Wipe homework/student/comment rows and re-seed lookups + admin user."""
    db = SessionLocal()
    try:
        db.query(Comment).delete()
        db.query(Student).delete()
        db.query(Homework).delete()
        db.query(User).delete()
        db.commit()
        seed_lookups(db)
    finally:
        db.close()


def db_count(model_cls) -> int:
    """Count rows in a table, used by tests that previously did `len(store.X) == 0`."""
    db = SessionLocal()
    try:
        return db.query(model_cls).count()
    finally:
        db.close()


# make sure the db starts clean before any test class runs
_reset_db()


# HEALTH
def test_root():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["status"] == "ProElev API is running"


# AUTH
class TestAuth:
    def test_login_success(self):
        r = client.post("/auth/login", json={"email": "admin@proelev.ro", "password": "Admin123"})
        assert r.status_code == 200
        assert r.json()["user"]["email"] == "admin@proelev.ro"

    def test_login_wrong_password(self):
        r = client.post("/auth/login", json={"email": "admin@proelev.ro", "password": "wrong"})
        assert r.status_code == 401

    def test_login_wrong_email(self):
        r = client.post("/auth/login", json={"email": "nobody@x.com", "password": "Admin123"})
        assert r.status_code == 401

    def test_login_empty_email(self):
        r = client.post("/auth/login", json={"email": "", "password": "Admin123"})
        assert r.status_code == 422

    def test_login_empty_password(self):
        r = client.post("/auth/login", json={"email": "admin@proelev.ro", "password": ""})
        assert r.status_code == 422


# HOMEWORKS
VALID_HW = {
    "title": "Ecuații liniare",
    "subject": "Matematică",
    "assignedClass": "1A",
    "dueDate": "2025-06-01",
    "description": "Rezolvați paginile 10-15.",
}


class TestHomeworks:
    def setup_method(self):
        """Fresh db before each test."""
        _reset_db()

    # CREATE
    def test_create_homework_success(self):
        r = client.post("/homeworks", json=VALID_HW)
        assert r.status_code == 201
        data = r.json()
        assert data["title"] == VALID_HW["title"]
        assert data["id"] == 1

    def test_create_homework_with_file_no_description(self):
        payload = {**VALID_HW, "description": None, "fileName": "file.pdf"}
        r = client.post("/homeworks", json=payload)
        assert r.status_code == 201

    def test_create_homework_missing_title(self):
        r = client.post("/homeworks", json={**VALID_HW, "title": ""})
        assert r.status_code == 422

    def test_create_homework_invalid_subject(self):
        r = client.post("/homeworks", json={**VALID_HW, "subject": "Fizică"})
        assert r.status_code == 422

    def test_create_homework_invalid_class(self):
        r = client.post("/homeworks", json={**VALID_HW, "assignedClass": "99Z"})
        assert r.status_code == 422

    def test_create_homework_invalid_date(self):
        r = client.post("/homeworks", json={**VALID_HW, "dueDate": "01-06-2025"})
        assert r.status_code == 422

    def test_create_homework_no_description_no_file(self):
        payload = {**VALID_HW, "description": None, "fileName": None}
        r = client.post("/homeworks", json=payload)
        assert r.status_code == 422

    def test_create_homework_title_too_long(self):
        r = client.post("/homeworks", json={**VALID_HW, "title": "x" * 201})
        assert r.status_code == 422

    # LIST
    def test_list_empty(self):
        r = client.get("/homeworks")
        assert r.status_code == 200
        assert r.json()["total"] == 0
        assert r.json()["items"] == []

    def test_list_pagination(self):
        for i in range(15):
            client.post("/homeworks", json={**VALID_HW, "title": f"Temă {i}"})
        r = client.get("/homeworks?page=1&pageSize=10")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 10
        assert r.json()["totalPages"] == 2

    def test_list_page_2(self):
        for i in range(15):
            client.post("/homeworks", json={**VALID_HW, "title": f"Temă {i}"})
        r = client.get("/homeworks?page=2&pageSize=10")
        assert len(r.json()["items"]) == 5

    def test_list_filter_subject(self):
        client.post("/homeworks", json=VALID_HW)
        client.post("/homeworks", json={**VALID_HW, "subject": "Istorie"})
        r = client.get("/homeworks?subject=Matematică")
        assert r.json()["total"] == 1

    def test_list_filter_class(self):
        client.post("/homeworks", json=VALID_HW)
        client.post("/homeworks", json={**VALID_HW, "assignedClass": "2B"})
        r = client.get("/homeworks?assignedClass=1A")
        assert r.json()["total"] == 1

    def test_list_invalid_page(self):
        r = client.get("/homeworks?page=0")
        assert r.status_code == 422

    # GET ONE
    def test_get_homework(self):
        client.post("/homeworks", json=VALID_HW)
        r = client.get("/homeworks/1")
        assert r.status_code == 200
        assert r.json()["id"] == 1

    def test_get_homework_not_found(self):
        r = client.get("/homeworks/999")
        assert r.status_code == 404

    # UPDATE
    def test_update_homework(self):
        client.post("/homeworks", json=VALID_HW)
        r = client.put("/homeworks/1", json={"title": "Titlu nou"})
        assert r.status_code == 200
        assert r.json()["title"] == "Titlu nou"

    def test_update_homework_not_found(self):
        r = client.put("/homeworks/999", json={"title": "X"})
        assert r.status_code == 404

    def test_update_homework_invalid_subject(self):
        client.post("/homeworks", json=VALID_HW)
        r = client.put("/homeworks/1", json={"subject": "Fizică"})
        assert r.status_code == 422

    def test_update_homework_empty_title(self):
        client.post("/homeworks", json=VALID_HW)
        r = client.put("/homeworks/1", json={"title": "   "})
        assert r.status_code == 422

    def test_update_homework_title_too_long(self):
        client.post("/homeworks", json=VALID_HW)
        r = client.put("/homeworks/1", json={"title": "x" * 201})
        assert r.status_code == 422

    def test_update_homework_invalid_class(self):
        client.post("/homeworks", json=VALID_HW)
        r = client.put("/homeworks/1", json={"assignedClass": "9Z"})
        assert r.status_code == 422

    def test_update_homework_invalid_date(self):
        client.post("/homeworks", json=VALID_HW)
        r = client.put("/homeworks/1", json={"dueDate": "not-a-date"})
        assert r.status_code == 422

    # DELETE
    def test_delete_homework(self):
        client.post("/homeworks", json=VALID_HW)
        r = client.delete("/homeworks/1")
        assert r.status_code == 204
        assert client.get("/homeworks/1").status_code == 404

    def test_delete_also_removes_students(self):
        client.post("/homeworks", json=VALID_HW)
        client.post("/homeworks/1/students", json={"name": "Ion", "dateTime": "2024-01-01 10:00"})
        client.delete("/homeworks/1")
        assert db_count(Student) == 0

    def test_delete_homework_not_found(self):
        r = client.delete("/homeworks/999")
        assert r.status_code == 404


# STUDENTS
VALID_STUDENT = {"name": "Ion Popescu", "dateTime": "2024-05-01 09:00", "grade": 8}


class TestStudents:
    def setup_method(self):
        # fresh db, create one homework so we have a parent for students,
        # then wipe just the auto-assigned roster so counts stay predictable
        _reset_db()
        client.post("/homeworks", json=VALID_HW)
        db = SessionLocal()
        try:
            db.query(Student).delete()
            db.commit()
        finally:
            db.close()

    # CREATE
    def test_add_student(self):
        r = client.post("/homeworks/1/students", json=VALID_STUDENT)
        assert r.status_code == 201
        assert r.json()["name"] == "Ion Popescu"

    def test_add_student_no_grade(self):
        r = client.post("/homeworks/1/students", json={"name": "Maria", "dateTime": "2024-05-01 10:00"})
        assert r.status_code == 201
        assert r.json()["grade"] is None

    def test_add_student_homework_not_found(self):
        r = client.post("/homeworks/999/students", json=VALID_STUDENT)
        assert r.status_code == 404

    def test_add_student_empty_name(self):
        r = client.post("/homeworks/1/students", json={**VALID_STUDENT, "name": ""})
        assert r.status_code == 422

    def test_add_student_grade_out_of_range(self):
        r = client.post("/homeworks/1/students", json={**VALID_STUDENT, "grade": 11})
        assert r.status_code == 422

    def test_add_student_grade_zero(self):
        r = client.post("/homeworks/1/students", json={**VALID_STUDENT, "grade": 0})
        assert r.status_code == 422

    # LIST
    def test_list_students_empty(self):
        r = client.get("/homeworks/1/students")
        assert r.json()["total"] == 0

    def test_list_students_pagination(self):
        for i in range(12):
            client.post("/homeworks/1/students", json={"name": f"Elev {i}", "dateTime": "2024-01-01 10:00"})
        r = client.get("/homeworks/1/students?page=1&pageSize=10")
        assert len(r.json()["items"]) == 10
        assert r.json()["totalPages"] == 2

    def test_list_students_homework_not_found(self):
        r = client.get("/homeworks/999/students")
        assert r.status_code == 404

    # GET ONE
    def test_get_student(self):
        client.post("/homeworks/1/students", json=VALID_STUDENT)
        r = client.get("/homeworks/1/students/1")
        assert r.status_code == 200

    def test_get_student_not_found(self):
        r = client.get("/homeworks/1/students/999")
        assert r.status_code == 404

    # UPDATE
    def test_update_student_grade(self):
        client.post("/homeworks/1/students", json=VALID_STUDENT)
        r = client.put("/homeworks/1/students/1", json={"grade": 10})
        assert r.status_code == 200
        assert r.json()["grade"] == 10

    def test_update_student_invalid_grade(self):
        client.post("/homeworks/1/students", json=VALID_STUDENT)
        r = client.put("/homeworks/1/students/1", json={"grade": 0})
        assert r.status_code == 422

    def test_update_student_empty_name(self):
        client.post("/homeworks/1/students", json=VALID_STUDENT)
        r = client.put("/homeworks/1/students/1", json={"name": "   "})
        assert r.status_code == 422

    def test_update_student_not_found(self):
        r = client.put("/homeworks/1/students/999", json={"grade": 5})
        assert r.status_code == 404

    # DELETE
    def test_delete_student(self):
        client.post("/homeworks/1/students", json=VALID_STUDENT)
        r = client.delete("/homeworks/1/students/1")
        assert r.status_code == 204

    def test_delete_student_not_found(self):
        r = client.delete("/homeworks/1/students/999")
        assert r.status_code == 404


# STATISTICS
class TestStatistics:
    def setup_method(self):
        # fresh db, create the parent homework, then wipe its auto-assigned students
        _reset_db()
        client.post("/homeworks", json=VALID_HW)
        db = SessionLocal()
        try:
            db.query(Student).delete()
            db.commit()
        finally:
            db.close()

    def test_statistics_no_students(self):
        r = client.get("/homeworks/1/statistics")
        assert r.status_code == 200
        data = r.json()
        assert data["totalStudents"] == 0
        assert data["passed"] == 0
        assert data["averageGrade"] is None

    def test_statistics_with_students(self):
        students = [
            {"name": "A", "dateTime": "2024-01-01 10:00", "grade": 9},
            {"name": "B", "dateTime": "2024-01-01 10:00", "grade": 4},
            {"name": "C", "dateTime": "2024-01-01 10:00", "grade": None},
        ]
        for s in students:
            client.post("/homeworks/1/students", json=s)

        r = client.get("/homeworks/1/statistics")
        assert r.status_code == 200
        data = r.json()
        assert data["totalStudents"] == 3
        assert data["passed"]   == 1
        assert data["failed"]   == 1
        assert data["ungraded"] == 1
        assert data["averageGrade"] == 6.5

    def test_statistics_homework_not_found(self):
        r = client.get("/homeworks/999/statistics")
        assert r.status_code == 404

    def test_grade_distribution_buckets(self):
        for grade in [10, 9, 8, 7, 6, 5, 3, None]:
            client.post("/homeworks/1/students", json={
                "name": f"Elev {grade}", "dateTime": "2024-01-01 10:00", "grade": grade
            })
        r = client.get("/homeworks/1/statistics")
        dist = {d["grade"]: d["count"] for d in r.json()["gradeDistribution"]}
        assert dist["10"] == 1
        assert dist["<5"] == 1
        assert dist["FĂRĂ NOTĂ"] == 1


# GENERATOR (start/stop/status)
class TestGenerator:
    def test_status_initial(self):
        r = client.get("/generator/status")
        assert r.status_code == 200
        assert "running" in r.json()

    def test_start_and_stop(self):
        r = client.post("/generator/start")
        assert r.status_code == 200
        assert r.json()["status"] in ("started", "already running")

        r = client.post("/generator/start")  # idempotent
        assert r.status_code == 200

        r = client.post("/generator/stop")
        assert r.status_code == 200
        assert r.json()["status"] == "stopped"



# WEBSOCKET (Silver requirement)
class TestWebSocket:
    def test_websocket_connect_and_disconnect(self):
        """Client can connect to /ws and the server registers + deregisters it."""
        import main
        before = len(main._ws_clients)
        with client.websocket_connect("/ws") as ws:
            # receive_text on the server side blocks until we send something
            ws.send_text("ping")
            # inside the context, the client is registered
            assert len(main._ws_clients) == before + 1
        # after disconnect, the server cleans up
        assert len(main._ws_clients) == before

    def test_broadcast_with_no_clients(self):
        """broadcast() should be a no-op when nobody is subscribed."""
        import main
        # ensure clean slate
        main._ws_clients.clear()
        # broadcast is async; run it to completion
        asyncio.run(main.broadcast({"event": "test", "payload": 1}))
        # no assertions beyond "didn't raise" — this exercises the for-loop entry
        assert main._ws_clients == []

    def test_broadcast_delivers_to_client(self):
        """A connected client receives broadcast messages."""
        import main
        with client.websocket_connect("/ws") as ws:
            asyncio.run(main.broadcast({"event": "new_batch", "homework": {"id": 42}}))
            msg = ws.receive_json()
            assert msg["event"] == "new_batch"
            assert msg["homework"]["id"] == 42


# COMMENTS (Gold — new 1-to-many: Homework → Comments, REST layer)
VALID_COMMENT = {"author": "Prof. Popescu", "text": "Foarte bine lucrat!"}


class TestComments:
    def setup_method(self):
        _reset_db()
        r = client.post("/homeworks", json=VALID_HW)
        self.hw_id = r.json()["id"]

    def test_create_comment(self):
        r = client.post(f"/homeworks/{self.hw_id}/comments", json=VALID_COMMENT)
        assert r.status_code == 201
        d = r.json()
        assert d["author"] == VALID_COMMENT["author"]
        assert d["text"]   == VALID_COMMENT["text"]
        assert d["homeworkId"] == self.hw_id
        assert "createdAt" in d

    def test_create_comment_hw_not_found(self):
        r = client.post("/homeworks/9999/comments", json=VALID_COMMENT)
        assert r.status_code == 404

    def test_create_comment_empty_author(self):
        r = client.post(f"/homeworks/{self.hw_id}/comments",
                        json={"author": "   ", "text": "x"})
        assert r.status_code == 422

    def test_create_comment_empty_text(self):
        r = client.post(f"/homeworks/{self.hw_id}/comments",
                        json={"author": "X", "text": "   "})
        assert r.status_code == 422

    def test_create_comment_author_too_long(self):
        r = client.post(f"/homeworks/{self.hw_id}/comments",
                        json={"author": "A" * 101, "text": "ok"})
        assert r.status_code == 422

    def test_create_comment_text_too_long(self):
        r = client.post(f"/homeworks/{self.hw_id}/comments",
                        json={"author": "X", "text": "a" * 1001})
        assert r.status_code == 422

    def test_list_comments_paginated(self):
        for i in range(3):
            client.post(f"/homeworks/{self.hw_id}/comments",
                        json={"author": f"A{i}", "text": f"t{i}"})
        r = client.get(f"/homeworks/{self.hw_id}/comments?page=1&pageSize=2")
        assert r.status_code == 200
        d = r.json()
        assert d["total"] == 3
        assert d["totalPages"] == 2
        assert len(d["items"]) == 2

    def test_list_comments_empty(self):
        r = client.get(f"/homeworks/{self.hw_id}/comments")
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_list_comments_hw_not_found(self):
        r = client.get("/homeworks/9999/comments")
        assert r.status_code == 404

    def test_get_comment(self):
        c = client.post(f"/homeworks/{self.hw_id}/comments", json=VALID_COMMENT).json()
        r = client.get(f"/homeworks/{self.hw_id}/comments/{c['id']}")
        assert r.status_code == 200
        assert r.json()["author"] == VALID_COMMENT["author"]

    def test_get_comment_not_found(self):
        r = client.get(f"/homeworks/{self.hw_id}/comments/9999")
        assert r.status_code == 404

    def test_update_comment(self):
        c = client.post(f"/homeworks/{self.hw_id}/comments", json=VALID_COMMENT).json()
        r = client.put(f"/homeworks/{self.hw_id}/comments/{c['id']}",
                       json={"text": "text modificat"})
        assert r.status_code == 200
        assert r.json()["text"] == "text modificat"

    def test_update_comment_not_found(self):
        r = client.put(f"/homeworks/{self.hw_id}/comments/9999", json={"text": "x"})
        assert r.status_code == 404

    def test_update_comment_empty_author(self):
        c = client.post(f"/homeworks/{self.hw_id}/comments", json=VALID_COMMENT).json()
        r = client.put(f"/homeworks/{self.hw_id}/comments/{c['id']}",
                       json={"author": "   "})
        assert r.status_code == 422

    def test_update_comment_empty_text(self):
        c = client.post(f"/homeworks/{self.hw_id}/comments", json=VALID_COMMENT).json()
        r = client.put(f"/homeworks/{self.hw_id}/comments/{c['id']}",
                       json={"text": "   "})
        assert r.status_code == 422

    def test_update_comment_text_too_long(self):
        c = client.post(f"/homeworks/{self.hw_id}/comments", json=VALID_COMMENT).json()
        r = client.put(f"/homeworks/{self.hw_id}/comments/{c['id']}",
                       json={"text": "a" * 1001})
        assert r.status_code == 422

    def test_delete_comment(self):
        c = client.post(f"/homeworks/{self.hw_id}/comments", json=VALID_COMMENT).json()
        r = client.delete(f"/homeworks/{self.hw_id}/comments/{c['id']}")
        assert r.status_code == 204
        assert client.get(f"/homeworks/{self.hw_id}/comments/{c['id']}").status_code == 404

    def test_delete_comment_not_found(self):
        r = client.delete(f"/homeworks/{self.hw_id}/comments/9999")
        assert r.status_code == 404

    def test_delete_homework_cascades_comments(self):
        client.post(f"/homeworks/{self.hw_id}/comments", json=VALID_COMMENT)
        client.post(f"/homeworks/{self.hw_id}/comments",
                    json={"author": "X", "text": "y"})
        client.delete(f"/homeworks/{self.hw_id}")
        assert db_count(Comment) == 0

    def test_comment_statistics_empty(self):
        r = client.get(f"/homeworks/{self.hw_id}/comments/statistics")
        assert r.status_code == 200
        d = r.json()
        assert d["totalComments"]     == 0
        assert d["uniqueAuthors"]     == 0
        assert d["averageTextLength"] == 0
        assert d["topAuthor"]         is None

    def test_comment_statistics_with_data(self):
        client.post(f"/homeworks/{self.hw_id}/comments",
                    json={"author": "Ana", "text": "bun"})           # 3
        client.post(f"/homeworks/{self.hw_id}/comments",
                    json={"author": "Ana", "text": "foarte bun"})    # 10
        client.post(f"/homeworks/{self.hw_id}/comments",
                    json={"author": "Bob", "text": "ok"})            # 2
        r = client.get(f"/homeworks/{self.hw_id}/comments/statistics")
        d = r.json()
        assert d["totalComments"] == 3
        assert d["uniqueAuthors"] == 2
        assert d["topAuthor"]     == "Ana"
        assert d["averageTextLength"] == round((3 + 10 + 2) / 3, 2)

    def test_comment_statistics_hw_not_found(self):
        r = client.get("/homeworks/9999/comments/statistics")
        assert r.status_code == 404


# GRAPHQL (Gold — same data/logic exposed via GraphQL)
def _gql(query: str, variables: dict | None = None):
    r = client.post("/graphql", json={"query": query, "variables": variables or {}})
    assert r.status_code == 200, r.text
    return r.json()


class TestGraphQLQueries:
    def setup_method(self):
        _reset_db()
# seed a homework via REST (so _auto_assign_students runs)
        r = client.post("/homeworks", json=VALID_HW)
        self.hw_id = r.json()["id"]

    def test_query_homeworks_paginated(self):
        d = _gql("""
          { homeworks(page: 1, pageSize: 5) {
              total page pageSize totalPages
              items { id title subject }
          } }""")
        assert d["data"]["homeworks"]["total"] == 1
        assert d["data"]["homeworks"]["items"][0]["title"] == VALID_HW["title"]

    def test_query_homeworks_with_filters(self):
        d = _gql("""
          query Q($s: String) { homeworks(subject: $s) { total } }""",
                 {"s": "Matematică"})
        assert d["data"]["homeworks"]["total"] == 1
        d = _gql("""
          query Q($s: String) { homeworks(subject: $s) { total } }""",
                 {"s": "Istorie"})
        assert d["data"]["homeworks"]["total"] == 0

    def test_query_homework_nested_students(self):
        d = _gql("""
          query Q($id: Int!) {
            homework(id: $id) { id title students { name grade } }
          }""", {"id": self.hw_id})
        hw = d["data"]["homework"]
        # class 1A has 11 students auto-assigned, most graded 1-10 and 2-3 left ungraded
        assert len(hw["students"]) == 11
        assert all(s["grade"] is None or 1 <= s["grade"] <= 10 for s in hw["students"])
        ungraded = sum(1 for s in hw["students"] if s["grade"] is None)
        assert 2 <= ungraded <= 3

    def test_query_homework_missing(self):
        d = _gql("{ homework(id: 9999) { id } }")
        assert d["data"]["homework"] is None

    def test_query_students(self):
        d = _gql("""
          query Q($id: Int!) {
            students(homeworkId: $id) { id name }
          }""", {"id": self.hw_id})
        assert len(d["data"]["students"]) == 11

    def test_query_homework_statistics(self):
        d = _gql("""
          query Q($id: Int!) {
            homeworkStatistics(homeworkId: $id) {
              homeworkId totalStudents ungraded averageGrade
              gradeDistribution { grade count }
            }
          }""", {"id": self.hw_id})
        s = d["data"]["homeworkStatistics"]
        assert s["totalStudents"] == 11
        # auto-assign gives most students a random grade 1-10 and leaves 2-3 ungraded
        assert 2 <= s["ungraded"] <= 3
        assert s["averageGrade"] is not None
        assert 1 <= s["averageGrade"] <= 10
        # 8 buckets: 10,9,8,7,6,5,<5,FĂRĂ NOTĂ
        assert len(s["gradeDistribution"]) == 8

    def test_query_homework_statistics_missing(self):
        d = _gql("{ homeworkStatistics(homeworkId: 9999) { homeworkId } }")
        assert "errors" in d

    def test_query_comments_and_stats(self):
        _gql("""
          mutation M($id: Int!) {
            createComment(homeworkId: $id, input: {author: "A", text: "hello"}) { id }
          }""", {"id": self.hw_id})
        d = _gql("""
          query Q($id: Int!) { comments(homeworkId: $id) { author text } }""",
                 {"id": self.hw_id})
        assert d["data"]["comments"][0]["author"] == "A"

        d = _gql("""
          query Q($id: Int!) {
            commentStatistics(homeworkId: $id) {
              totalComments uniqueAuthors topAuthor averageTextLength
            }
          }""", {"id": self.hw_id})
        s = d["data"]["commentStatistics"]
        assert s["totalComments"] == 1
        assert s["topAuthor"] == "A"

    def test_query_comments_hw_missing(self):
        d = _gql("{ comments(homeworkId: 9999) { id } }")
        assert "errors" in d


class TestGraphQLMutations:
    def setup_method(self):
        _reset_db()

    def test_create_homework_mutation(self):
        d = _gql("""
          mutation M($input: HomeworkInput!) {
            createHomework(input: $input) {
              id title subject students { name }
            }
          }""", {"input": VALID_HW})
        hw = d["data"]["createHomework"]
        assert hw["id"] == 1
        # _auto_assign_students must still run
        assert len(hw["students"]) == 11

    def test_create_homework_invalid(self):
        bad = dict(VALID_HW, subject="InvalidSubject")
        d = _gql("""
          mutation M($input: HomeworkInput!) {
            createHomework(input: $input) { id }
          }""", {"input": bad})
        assert "errors" in d

    def test_update_homework_mutation(self):
        _gql("""
          mutation M($i: HomeworkInput!) {
            createHomework(input: $i) { id }
          }""", {"i": VALID_HW})
        d = _gql("""
          mutation M($id: Int!, $p: HomeworkPatch!) {
            updateHomework(id: $id, patch: $p) { title }
          }""", {"id": 1, "p": {"title": "Nou"}})
        assert d["data"]["updateHomework"]["title"] == "Nou"

    def test_update_homework_missing(self):
        d = _gql("""
          mutation M { updateHomework(id: 9999, patch: {title: "x"}) { id } }""")
        assert "errors" in d

    def test_update_homework_invalid_class(self):
        _gql("""
          mutation M($i: HomeworkInput!) {
            createHomework(input: $i) { id }
          }""", {"i": VALID_HW})
        d = _gql("""
          mutation M { updateHomework(id: 1, patch: {assignedClass: "9X"}) { id } }""")
        assert "errors" in d

    def test_delete_homework_mutation_cascades(self):
        _gql("""
          mutation M($i: HomeworkInput!) {
            createHomework(input: $i) { id }
          }""", {"i": VALID_HW})
        # add a comment to verify cascade
        _gql("""
          mutation M {
            createComment(homeworkId: 1, input: {author: "A", text: "c"}) { id }
          }""")
        d = _gql("mutation { deleteHomework(id: 1) }")
        assert d["data"]["deleteHomework"] is True
        assert db_count(Comment) == 0
        assert db_count(Student) == 0

    def test_delete_homework_missing(self):
        d = _gql("mutation { deleteHomework(id: 9999) }")
        assert "errors" in d

    def test_student_crud_via_graphql(self):
        _gql("""
          mutation M($i: HomeworkInput!) {
            createHomework(input: $i) { id }
          }""", {"i": VALID_HW})
        # create
        d = _gql("""
          mutation M {
            createStudent(
              homeworkId: 1,
              input: {name: "Ion", dateTime: "2026-04-23 10:00", grade: 9}
            ) { id name grade }
          }""")
        sid = d["data"]["createStudent"]["id"]
        assert d["data"]["createStudent"]["grade"] == 9
        # update
        d = _gql("""
          mutation M($sid: Int!) {
            updateStudent(homeworkId: 1, id: $sid, patch: {grade: 10}) { grade }
          }""", {"sid": sid})
        assert d["data"]["updateStudent"]["grade"] == 10
        # delete
        d = _gql("""
          mutation M($sid: Int!) {
            deleteStudent(homeworkId: 1, id: $sid)
          }""", {"sid": sid})
        assert d["data"]["deleteStudent"] is True

    def test_create_student_hw_missing(self):
        d = _gql("""
          mutation M {
            createStudent(homeworkId: 9999,
              input: {name: "x", dateTime: "2026-04-23 10:00"}) { id }
          }""")
        assert "errors" in d

    def test_create_student_invalid_grade(self):
        _gql("""
          mutation M($i: HomeworkInput!) {
            createHomework(input: $i) { id }
          }""", {"i": VALID_HW})
        d = _gql("""
          mutation M {
            createStudent(homeworkId: 1,
              input: {name: "x", dateTime: "2026-04-23 10:00", grade: 99}) { id }
          }""")
        assert "errors" in d

    def test_update_student_not_found(self):
        _gql("""
          mutation M($i: HomeworkInput!) {
            createHomework(input: $i) { id }
          }""", {"i": VALID_HW})
        d = _gql("""
          mutation M {
            updateStudent(homeworkId: 1, id: 9999, patch: {grade: 7}) { id }
          }""")
        assert "errors" in d

    def test_delete_student_not_found(self):
        _gql("""
          mutation M($i: HomeworkInput!) {
            createHomework(input: $i) { id }
          }""", {"i": VALID_HW})
        d = _gql("""
          mutation M { deleteStudent(homeworkId: 1, id: 9999) }""")
        assert "errors" in d

    def test_comment_crud_via_graphql(self):
        _gql("""
          mutation M($i: HomeworkInput!) {
            createHomework(input: $i) { id }
          }""", {"i": VALID_HW})
        d = _gql("""
          mutation M {
            createComment(homeworkId: 1, input: {author: "Prof", text: "bun"}) {
              id author text createdAt
            }
          }""")
        cid = d["data"]["createComment"]["id"]
        assert d["data"]["createComment"]["author"] == "Prof"

        d = _gql("""
          mutation M($cid: Int!) {
            updateComment(homeworkId: 1, id: $cid, patch: {text: "foarte bun"}) { text }
          }""", {"cid": cid})
        assert d["data"]["updateComment"]["text"] == "foarte bun"

        d = _gql("""
          mutation M($cid: Int!) {
            deleteComment(homeworkId: 1, id: $cid)
          }""", {"cid": cid})
        assert d["data"]["deleteComment"] is True

    def test_comment_validation_fails(self):
        _gql("""
          mutation M($i: HomeworkInput!) {
            createHomework(input: $i) { id }
          }""", {"i": VALID_HW})
        d = _gql("""
          mutation M {
            createComment(homeworkId: 1, input: {author: "", text: "x"}) { id }
          }""")
        assert "errors" in d

    def test_update_comment_not_found(self):
        _gql("""
          mutation M($i: HomeworkInput!) {
            createHomework(input: $i) { id }
          }""", {"i": VALID_HW})
        d = _gql("""
          mutation M {
            updateComment(homeworkId: 1, id: 9999, patch: {text: "x"}) { id }
          }""")
        assert "errors" in d

    def test_delete_comment_not_found(self):
        _gql("""
          mutation M($i: HomeworkInput!) {
            createHomework(input: $i) { id }
          }""", {"i": VALID_HW})
        d = _gql("""
          mutation M { deleteComment(homeworkId: 1, id: 9999) }""")
        assert "errors" in d

    def test_create_comment_hw_missing(self):
        d = _gql("""
          mutation M {
            createComment(homeworkId: 9999, input: {author: "A", text: "t"}) { id }
          }""")
        assert "errors" in d
