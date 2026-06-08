# ProElev

A full-stack school management web app — Vue 3 (Composition API) frontend, FastAPI + SQLAlchemy backend, SQLite storage. Built for the *Perseverența duce la reușite!* school project contest.

**Live demo**
- Frontend: https://proelev.netlify.app (Netlify)
- Backend: https://proelev-backend.onrender.com (Render free tier)

---

## What it does

ProElev models a real primary school with five user roles, each seeing only what they're supposed to. The platform handles the entire lifecycle of a homework: a teacher posts it for their class, every student in the class is automatically enrolled, students upload their submission (text and/or a file), the teacher grades and writes feedback, and parents see the result for their child. Everything triggers a real-time notification.

### Roles

| Role     | Sees                                                                 |
|----------|----------------------------------------------------------------------|
| Admin    | Everything; can generate invite codes and manage users               |
| Teacher  | Only homeworks for the (class, subject) pairs they're assigned to    |
| Student  | Only homeworks for their own class; only their own submission        |
| Parent   | Only homeworks for their children's classes; only their child's grade and feedback |
| User     | Legacy read-only role (still works for backwards compatibility)      |

### Features

- **Registration with invite codes.** Admin generates one-time codes (7-day TTL) that determine the new account's role and lock in the class/subject. Without a code, registration produces a legacy "user" account.
- **3-factor login.** Password + email-OTP code + security-question answer.
- **Sliding token refresh.** Every successful request bumps a server-side session expiry; logout actually invalidates the token.
- **Defensive middleware.** Rate limiting, request-size cap, security headers, login throttle, WebSocket flood guard.
- **Audit log + anomaly detector.** Every request is logged; an `IsolationForest` model runs every 30s and flags users with abnormal traffic patterns.
- **Homework lifecycle.** Create with optional PDF/image attachment, role-aware listing, grading with feedback, statistics with pie chart.
- **Chat.** WebSocket-based DMs and group rooms, plus a global lobby.
- **Notifications.** Bell in the header with a red unread badge; every important event (homework created, submission uploaded, grade given, chat message) fans out to a notification row per recipient.
- **CATALOG (gradebook).** Per-role aggregator — student/parent sees all their grades and averages, teacher/admin sees a full student × homework matrix.
- **ORAR (timetable).** Weekly schedule per class with subject + teacher names pulled from real assignments.
- **Comments.** GraphQL-served comment thread on each homework.
- **Performance demo.** A heavy stats endpoint with three implementations (naive / indexed / cached) so the speed difference is visible.

---

## Demo accounts

Every demo account uses the same security question — answer is **`proelev`**.

| Email                 | Password   | Role     |
|-----------------------|------------|----------|
| admin@proelev.ro      | Admin123   | admin    |
| user@proelev.ro       | Parola123  | user     |
| prof@proelev.ro       | Profesor1  | teacher  |
| elev@proelev.ro       | Elev1234   | student  |
| parinte@proelev.ro    | Parinte1   | parent   |

Demo relationships seeded on boot:
- **prof@** teaches *Matematică* for class *4A*.
- **elev@** is in class *4A*.
- **parinte@** is the parent of **elev@**.

The seeder also creates three demo homeworks on first boot:
1. *Exerciții cu fracții ordinare* — past due, already graded with a 9.
2. *Probleme de geometrie - triunghiuri* — current, submitted but ungraded.
3. *Test recapitulativ - unități de măsură* — upcoming, not yet submitted.

So a judge logging in as the student or the parent immediately sees grades, feedback, and an active homework pipeline.

---

## 5-minute demo script

This walks every feature in roughly five minutes.

1. **Open the live frontend.** Land on the homepage; observe the marketing copy.
2. **Log in as `admin@proelev.ro`.** Show the 3-factor flow (password → email code from the in-app inbox → security question).
3. **Open `/admin`.** Generate a teacher invite code with preset class *4A* and subject *Matematică*; copy the code.
4. **Log out.** Open `/register`, paste the code, fill the rest — show how the form auto-detects the teacher fields.
5. **Log in as `prof@proelev.ro`** (the existing demo teacher). Open `/main` to show the role-aware dashboard. Click on **TEME** and notice the listing only shows the teacher's *Matematică 4A* homeworks.
6. **Create a new homework** for *Matematică 4A*. Attach a PDF using the file picker so the demo also covers the attachment feature.
7. **Log out and log in as `elev@proelev.ro`.** Open the new homework. Notice it appeared in NOTIFICĂRI (red badge on the bell, the new item is tinted blue). Submit a text response + optional file.
8. **Log back in as `prof@proelev.ro`.** Notice a "Tema a fost trimisă" notification fired. Open the homework, see the student's submission text, download their file, give a grade and feedback.
9. **Log in as `parinte@proelev.ro`.** Open `/catalog` to see the child's grades aggregated, including the one we just gave. Open the homework detail to see the parent card — child name, submission status, grade, feedback. Notice the parent never sees other students.
10. **Open `/orar` from the sidebar** to show the weekly timetable.

Total: roughly 5 minutes, hits all 5 roles plus every major feature.

---

## Running locally

```bash
# backend
cd src/backend
pip install -r requirements.txt
python -m alembic upgrade head
python -m uvicorn main:app --reload

# frontend (separate terminal)
npm install
npm run dev
```

The frontend talks to `http://localhost:8000` by default. To point it at a different backend (e.g. for a cross-machine demo), set `VITE_API_URL` in `.env.local`.

### Tests

```bash
cd src/backend
python -m pytest test_roles.py test_notifications.py test_catalog_orar.py
```

42 tests cover the role system, notification fan-out, gradebook shape per role, timetable, and homework attachments.

---

## Architecture quick tour

- `src/backend/models.py` — SQLAlchemy models. 3NF, lookup tables for subjects/classes, M2M for `teacher_assignment` and `parent_child`, audit log + anomaly observation.
- `src/backend/routers/` — one router per resource. `homeworks`, `students` (submission/grading), `gradebook`, `timetable`, `notifications`, `invites`, `chat`, `comments`, `auth`, `admin`, plus defense bits.
- `src/backend/role_filters.py` — single source of truth for "what can role X see/edit". Every list endpoint and every write endpoint goes through these helpers.
- `src/backend/defense_middleware.py` — rate limit + size cap + security headers.
- `src/backend/audit_middleware.py` — logs every request and feeds the anomaly detector.
- `src/backend/ai_detector.py` — background `IsolationForest` thread that auto-revokes the session of any user whose request volume looks bot-like.
- `src/views/` — one Vue 3 file per page. Composition API throughout.
- `src/components/` — small reusable bits (Header, Sidebar, Profile menu, NotificationBell, ChatNotification).
- `src/api.js` — every backend call lives here; handles bearer token, sliding refresh, and offline queueing.

---

## Tech stack

- **Frontend:** Vue 3, Vite, Vue Router, plain CSS (no UI library).
- **Backend:** FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic, Strawberry GraphQL.
- **Auth:** JWT (PyJWT), bcrypt password hashing, server-side session records for revocation.
- **Storage:** SQLite (dev + Render free tier); file uploads stored as `LargeBinary` blobs in the database so they survive ephemeral filesystems.
- **Realtime:** WebSocket for chat with a flood guard.
- **ML:** scikit-learn `IsolationForest` for the anomaly detector.

---

## Development notes

This project was built incrementally across six assignments. The earlier README content (Vite scaffolding boilerplate) has been replaced by this one; see `git log` for the full history.

```sh
npm install              # install frontend deps
npm run dev              # vite dev server on :5173
npm run build            # production build to dist/
```
