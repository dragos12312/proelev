# sqlalchemy orm models
# strict 3nf, subject and school_class are lookup tables so the homework row
# doesnt repeat the same string over and over
#
# tables and relationships
#   subject       1 -- many homework
#   school_class  1 -- many homework
#   homework      1 -- many student
#   homework      1 -- many comment
#   user          standalone, no fks
from sqlalchemy import (
    Column, Integer, String, Date, DateTime, ForeignKey, UniqueConstraint, CheckConstraint, Table, Index,
    LargeBinary, Text,
)
from sqlalchemy.orm import relationship

from database import Base


# many to many junction between role and permission
# kept as a plain Table since it has no extra columns of its own
role_permission = Table(
    "role_permission", Base.metadata,
    Column("role_id",       Integer, ForeignKey("role.id",       ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permission.id", ondelete="CASCADE"), primary_key=True),
)


# assignment 5 gold, many to many between student submissions and tags
# the heavy compute stat aggregates grades by tag across the m2m, which is
# slow until we add indices and caching
student_tag = Table(
    "student_tag", Base.metadata,
    Column("student_id", Integer, ForeignKey("student.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id",     Integer, ForeignKey("tag.id",     ondelete="CASCADE"), primary_key=True),
)


# assignment 6, teacher gets a list of (class, subject) pairs they teach
# composite PK lets the same teacher be assigned to multiple combinations
teacher_assignment = Table(
    "teacher_assignment", Base.metadata,
    Column("user_id",    Integer, ForeignKey("user.id",         ondelete="CASCADE"), primary_key=True),
    Column("class_id",   Integer, ForeignKey("school_class.id", ondelete="CASCADE"), primary_key=True),
    Column("subject_id", Integer, ForeignKey("subject.id",      ondelete="CASCADE"), primary_key=True),
)


# assignment 6, parents link to one or more children, children can have
# multiple parents (siblings / divorced parents both work)
parent_child = Table(
    "parent_child", Base.metadata,
    Column("parent_user_id", Integer, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
    Column("child_user_id",  Integer, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
)


# a role groups a set of permissions, every user has exactly one role
class Role(Base):
    __tablename__ = "role"

    id   = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True)

    permissions = relationship("Permission", secondary=role_permission, back_populates="roles")
    users       = relationship("User", back_populates="role")


# one row per discrete capability, like homework_create or comment_delete
class Permission(Base):
    __tablename__ = "permission"

    id   = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(80), nullable=False, unique=True)

    roles = relationship("Role", secondary=role_permission, back_populates="permissions")


# lookup table for the seven school subjects
class Subject(Base):
    __tablename__ = "subject"

    id   = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)

    homeworks = relationship("Homework", back_populates="subject")


# lookup table for the eight classes 1A through 4B
class SchoolClass(Base):
    __tablename__ = "school_class"

    id   = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(10), nullable=False, unique=True)

    homeworks = relationship("Homework", back_populates="assigned_class")


# main entity, references subject and school_class by foreign key
class Homework(Base):
    __tablename__ = "homework"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    title       = Column(String(200), nullable=False)
    subject_id  = Column(Integer, ForeignKey("subject.id",      ondelete="RESTRICT"), nullable=False)
    class_id    = Column(Integer, ForeignKey("school_class.id", ondelete="RESTRICT"), nullable=False)
    due_date    = Column(Date, nullable=False)
    description = Column(String, nullable=True)
    file_name   = Column(String(255), nullable=True)
    # assignment 6, the actual bytes of the attached file (pdf/image) so it
    # survives Render's ephemeral filesystem. null when the teacher didn't
    # attach anything.
    file_blob   = Column(LargeBinary, nullable=True)
    # assignment 6, the teacher who posted this homework, null for legacy / admin posts
    created_by_user_id = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)

    subject        = relationship("Subject",     back_populates="homeworks")
    assigned_class = relationship("SchoolClass", back_populates="homeworks")
    created_by     = relationship("User",        foreign_keys=[created_by_user_id])
    students = relationship(
        "Student", back_populates="homework",
        cascade="all, delete-orphan", passive_deletes=True,
    )
    comments = relationship(
        "Comment", back_populates="homework",
        cascade="all, delete-orphan", passive_deletes=True,
    )


# one row per student per homework, grade can be null when not yet marked
# assignment 6 adds the submission fields, the row IS the submission record
# user_id links to the User account of the student (nullable for legacy rows)
class Student(Base):
    __tablename__ = "student"

    id                   = Column(Integer, primary_key=True, autoincrement=True)
    homework_id          = Column(Integer, ForeignKey("homework.id", ondelete="CASCADE"), nullable=False)
    user_id              = Column(Integer, ForeignKey("user.id",     ondelete="SET NULL"), nullable=True)
    name                 = Column(String(150), nullable=False)
    date_time            = Column(String(20), nullable=False)
    grade                = Column(Integer, nullable=True)
    # assignment 6 submission, set when the student uploads
    submitted_at         = Column(DateTime, nullable=True)
    submission_text      = Column(Text,     nullable=True)
    submission_file_name = Column(String(255), nullable=True)
    submission_blob      = Column(LargeBinary, nullable=True)
    # assignment 6, teacher feedback alongside the grade
    feedback             = Column(Text, nullable=True)

    __table_args__ = (
        # grade must be between 1 and 10 if present, enforced at the db level too
        CheckConstraint("grade IS NULL OR (grade >= 1 AND grade <= 10)", name="ck_student_grade_range"),
    )

    homework = relationship("Homework", back_populates="students")
    tags     = relationship("Tag", secondary=student_tag, back_populates="students")
    user     = relationship("User", foreign_keys=[user_id])


# assignment 5 gold, lookup table of short labels describing a submission
# such as "olimpic", "restantier", "bursier", "lider_clasă"
class Tag(Base):
    __tablename__ = "tag"

    id   = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True)

    students = relationship("Student", secondary=student_tag, back_populates="tags")


# 1 to many with homework, the new entity i added for the assignment
class Comment(Base):
    __tablename__ = "comment"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    homework_id = Column(Integer, ForeignKey("homework.id", ondelete="CASCADE"), nullable=False)
    author      = Column(String(100), nullable=False)
    text        = Column(String(2000), nullable=False)
    created_at  = Column(String(20), nullable=False)

    homework = relationship("Homework", back_populates="comments")


# user table, every user has a role which carries the permission set
# security_question + security_answer_hash power factor #3 of the login flow
# and the password recovery question
# assignment 6 adds class_id (for student users), plus M2M to teacher_assignment
# (for teacher users) and parent_child (for parents and children both ways)
class User(Base):
    __tablename__ = "user"

    id                   = Column(Integer, primary_key=True, autoincrement=True)
    email                = Column(String(150), nullable=False, unique=True)
    # bcrypt produces 60 char hashes, give it some headroom for future scheme bumps
    password_hash        = Column(String(255), nullable=False)
    name                 = Column(String(150), nullable=False)
    role_id              = Column(Integer, ForeignKey("role.id", ondelete="RESTRICT"), nullable=False)
    security_question    = Column(String(255), nullable=True)
    security_answer_hash = Column(String(255), nullable=True)
    class_id             = Column(Integer, ForeignKey("school_class.id", ondelete="SET NULL"), nullable=True)

    role = relationship("Role", back_populates="users")
    school_class = relationship("SchoolClass", foreign_keys=[class_id])

    # teacher only: what (class, subject) pairs they're allowed to teach
    teacher_classes = relationship(
        "SchoolClass", secondary=teacher_assignment,
        primaryjoin="User.id == teacher_assignment.c.user_id",
        secondaryjoin="SchoolClass.id == teacher_assignment.c.class_id",
        viewonly=True,
    )
    teacher_subjects = relationship(
        "Subject", secondary=teacher_assignment,
        primaryjoin="User.id == teacher_assignment.c.user_id",
        secondaryjoin="Subject.id == teacher_assignment.c.subject_id",
        viewonly=True,
    )

    # parent side: list of child users
    children = relationship(
        "User", secondary=parent_child,
        primaryjoin="User.id == parent_child.c.parent_user_id",
        secondaryjoin="User.id == parent_child.c.child_user_id",
        back_populates="parents",
    )
    # child side: list of parent users
    parents = relationship(
        "User", secondary=parent_child,
        primaryjoin="User.id == parent_child.c.child_user_id",
        secondaryjoin="User.id == parent_child.c.parent_user_id",
        back_populates="children",
    )


# silver, server side session record so logout actually invalidates a token
# every issued JWT carries a jti that references one of these rows
class Session(Base):
    __tablename__ = "session"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    user_id        = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    jti            = Column(String(64), nullable=False, unique=True)
    created_at     = Column(DateTime, nullable=False)
    last_active_at = Column(DateTime, nullable=False)
    revoked        = Column(Integer, nullable=False, default=0)  # 0/1 since sqlite has no bool


# silver, 3 factor login wizard state machine
# each successful factor unlocks the next, the row carries the email code
# and the temp challenge id the client passes between steps
class LoginChallenge(Base):
    __tablename__ = "login_challenge"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    user_id         = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    challenge_id    = Column(String(64), nullable=False, unique=True)
    email_code      = Column(String(10), nullable=False)
    email_verified  = Column(Integer, nullable=False, default=0)
    completed       = Column(Integer, nullable=False, default=0)
    created_at      = Column(DateTime, nullable=False)
    expires_at      = Column(DateTime, nullable=False)


# silver, single use password reset tokens, expire 30 minutes from creation
class PasswordReset(Base):
    __tablename__ = "password_reset"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    user_id      = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    token        = Column(String(64), nullable=False, unique=True)
    expires_at   = Column(DateTime, nullable=False)
    used         = Column(Integer, nullable=False, default=0)
    created_at   = Column(DateTime, nullable=False)


# assignment 6, invite codes the admin generates for teacher/student/parent
# self-registration. each code locks down the role the new account will have,
# and can optionally preset a class (student) or subject (teacher).
# default lifetime is 7 days, single use.
class InviteCode(Base):
    __tablename__ = "invite_code"

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    code               = Column(String(32), nullable=False, unique=True)
    role_name          = Column(String(50), nullable=False)
    class_id           = Column(Integer, ForeignKey("school_class.id", ondelete="SET NULL"), nullable=True)
    subject_id         = Column(Integer, ForeignKey("subject.id",      ondelete="SET NULL"), nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("user.id",         ondelete="SET NULL"), nullable=True)
    used_by_user_id    = Column(Integer, ForeignKey("user.id",         ondelete="SET NULL"), nullable=True)
    created_at         = Column(DateTime, nullable=False)
    expires_at         = Column(DateTime, nullable=False)
    used_at            = Column(DateTime, nullable=True)
    revoked            = Column(Integer,  nullable=False, default=0)

    preset_class   = relationship("SchoolClass", foreign_keys=[class_id])
    preset_subject = relationship("Subject",     foreign_keys=[subject_id])
    created_by     = relationship("User",        foreign_keys=[created_by_user_id])
    used_by        = relationship("User",        foreign_keys=[used_by_user_id])


# gold, audit log of every request that touches the api
# user_id and role_id are nullable so we can log anonymous hits like /auth/login
# created_at is indexed so the detector can do fast time window queries
class ActionLog(Base):
    __tablename__ = "action_log"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    user_id     = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    role_id     = Column(Integer, ForeignKey("role.id", ondelete="SET NULL"), nullable=True)
    action      = Column(String(100), nullable=False)   # short code like homework.delete
    target_type = Column(String(50),  nullable=True)    # homework, comment, student
    target_id   = Column(Integer,     nullable=True)
    method      = Column(String(10),  nullable=False)
    path        = Column(String(255), nullable=False)
    status_code = Column(Integer,     nullable=False)
    ip_address  = Column(String(64),  nullable=True)
    details     = Column(String,      nullable=True)    # json blob for extras
    created_at  = Column(DateTime,    nullable=False)
    # if the same user fires the exact same action twice in a row we bump the
    # existing row instead of inserting a new one, count is the number of hits
    # last_seen_at is the timestamp of the most recent hit
    count        = Column(Integer,    nullable=False, default=1)
    last_seen_at = Column(DateTime,   nullable=True)

    user = relationship("User",  foreign_keys=[user_id])
    role = relationship("Role",  foreign_keys=[role_id])

    __table_args__ = (
        # the detector queries by user and time, this index makes that O(log n)
        Index("ix_action_log_user_time", "user_id", "created_at"),
        Index("ix_action_log_created_at", "created_at"),
        Index("ix_action_log_user_last_seen", "user_id", "last_seen_at"),
    )


# assignment 6 polish, daily attendance. one row per (class, student, day).
# unique constraint keeps the teacher from accidentally marking the same kid
# twice for the same morning. status is "present" / "absent" / "late" /
# "excused" — kept as a string so we don't burn a migration on new states.
class Attendance(Base):
    __tablename__ = "attendance"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    class_id          = Column(Integer, ForeignKey("school_class.id", ondelete="CASCADE"), nullable=False)
    student_user_id   = Column(Integer, ForeignKey("user.id",         ondelete="CASCADE"), nullable=False)
    date              = Column(Date,    nullable=False)
    status            = Column(String(20), nullable=False)
    note              = Column(String(255), nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at        = Column(DateTime, nullable=False)

    school_class = relationship("SchoolClass", foreign_keys=[class_id])
    student      = relationship("User",        foreign_keys=[student_user_id])
    created_by   = relationship("User",        foreign_keys=[created_by_user_id])

    __table_args__ = (
        UniqueConstraint("class_id", "student_user_id", "date", name="uq_attendance_class_student_date"),
        Index("ix_attendance_class_date",   "class_id",        "date"),
        Index("ix_attendance_student_date", "student_user_id", "date"),
    )


# assignment 6 polish, "media la purtare" — Romanian schools track a
# behavior grade alongside academic grades. one row per (student, period);
# period is a free-form string like "Semestrul 1 2025-2026" so we don't
# burn migrations later.
class BehaviorGrade(Base):
    __tablename__ = "behavior_grade"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    student_user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    period          = Column(String(64), nullable=False)
    grade           = Column(Integer, nullable=False)
    note            = Column(Text, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at      = Column(DateTime, nullable=False)

    student    = relationship("User", foreign_keys=[student_user_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])

    __table_args__ = (
        UniqueConstraint("student_user_id", "period", name="uq_behavior_grade_student_period"),
        CheckConstraint("grade >= 1 AND grade <= 10", name="ck_behavior_grade_range"),
    )


# School-wide announcement. Admin (or "user" legacy role) posts one and it
# fans out to every page header / dashboard. Distinct from per-channel
# anunțuri which are scoped to (class, subject).
class SchoolAnnouncement(Base):
    __tablename__ = "school_announcement"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    title           = Column(String(200), nullable=False)
    body            = Column(Text, nullable=True)
    kind            = Column(String(20), nullable=False, default="info")  # info/warning/event
    created_by_user_id = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at      = Column(DateTime, nullable=False)
    pinned          = Column(Integer, nullable=False, default=1)  # 0 archived, 1 visible

    created_by = relationship("User", foreign_keys=[created_by_user_id])


# assignment 6 polish, formal tests (separate from homeworks). A teacher
# announces a test for a (class, subject) pair on a given date (which is
# allowed to be in the past so the contest demo can show "the last test was
# 3 weeks ago, the new one is today"). Each student gets a TestGrade row
# once the teacher fills it in.
class Test(Base):
    __tablename__ = "test"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    class_id        = Column(Integer, ForeignKey("school_class.id", ondelete="CASCADE"), nullable=False)
    subject_id      = Column(Integer, ForeignKey("subject.id",      ondelete="CASCADE"), nullable=False)
    title           = Column(String(200), nullable=False)
    description     = Column(Text, nullable=True)
    scheduled_date  = Column(Date, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at      = Column(DateTime, nullable=False)

    school_class = relationship("SchoolClass", foreign_keys=[class_id])
    subject      = relationship("Subject",     foreign_keys=[subject_id])
    created_by   = relationship("User",        foreign_keys=[created_by_user_id])
    grades       = relationship("TestGrade", back_populates="test",
                                cascade="all, delete-orphan", passive_deletes=True)

    __table_args__ = (
        Index("ix_test_class_subject_date", "class_id", "subject_id", "scheduled_date"),
    )


class TestGrade(Base):
    __tablename__ = "test_grade"

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    test_id            = Column(Integer, ForeignKey("test.id", ondelete="CASCADE"), nullable=False)
    student_user_id    = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    grade              = Column(Integer, nullable=True)
    feedback           = Column(Text,    nullable=True)
    graded_by_user_id  = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    graded_at          = Column(DateTime, nullable=True)

    test    = relationship("Test", back_populates="grades", foreign_keys=[test_id])
    student = relationship("User", foreign_keys=[student_user_id])

    __table_args__ = (
        UniqueConstraint("test_id", "student_user_id", name="uq_test_grade_test_student"),
        CheckConstraint("grade IS NULL OR (grade >= 1 AND grade <= 10)", name="ck_test_grade_range"),
        Index("ix_test_grade_student", "student_user_id"),
    )


# A "big improvement" event — recorded when a fresh test grade is at least
# 3 points higher than the student's previous test grade in the same subject.
# The splash component polls for unack'd rows; once the student dismisses
# the splash, ack_at is set so it never fires again.
class TestImprovement(Base):
    __tablename__ = "test_improvement"

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    student_user_id    = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    subject_id         = Column(Integer, ForeignKey("subject.id", ondelete="CASCADE"), nullable=False)
    previous_test_id   = Column(Integer, ForeignKey("test.id", ondelete="SET NULL"), nullable=True)
    new_test_id        = Column(Integer, ForeignKey("test.id", ondelete="CASCADE"), nullable=False)
    old_grade          = Column(Integer, nullable=False)
    new_grade          = Column(Integer, nullable=False)
    created_at         = Column(DateTime, nullable=False)
    ack_at             = Column(DateTime, nullable=True)

    student = relationship("User",    foreign_keys=[student_user_id])
    subject = relationship("Subject", foreign_keys=[subject_id])
    new_test = relationship("Test",   foreign_keys=[new_test_id])

    __table_args__ = (
        Index("ix_test_improvement_student_ack", "student_user_id", "ack_at"),
    )


# assignment 6 polish, MS-Teams-style per-(class, subject) channel with two
# kinds of rows: text posts ("post") and resource files ("file"). everyone
# enrolled in that (class, subject) can read; teachers + admins can post
# and upload, students can post but not upload, parents are read-only.
class SubjectChannelPost(Base):
    __tablename__ = "subject_channel_post"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    class_id        = Column(Integer, ForeignKey("school_class.id", ondelete="CASCADE"), nullable=False)
    subject_id      = Column(Integer, ForeignKey("subject.id",      ondelete="CASCADE"), nullable=False)
    author_user_id  = Column(Integer, ForeignKey("user.id",         ondelete="SET NULL"), nullable=True)
    kind            = Column(String(10),  nullable=False)   # "post" or "file"
    text            = Column(Text,        nullable=True)
    file_name       = Column(String(255), nullable=True)
    file_blob       = Column(LargeBinary, nullable=True)
    created_at      = Column(DateTime,    nullable=False)

    school_class = relationship("SchoolClass", foreign_keys=[class_id])
    subject      = relationship("Subject",     foreign_keys=[subject_id])
    author       = relationship("User",        foreign_keys=[author_user_id])

    __table_args__ = (
        Index("ix_channel_post_channel_created", "class_id", "subject_id", "created_at"),
    )


# assignment 6, per-user notifications. one row per event delivered to one
# recipient (so a single homework triggers N rows, one per student + parent).
# read_at is null until the user clicks it / marks all read.
class Notification(Base):
    __tablename__ = "notification"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    user_id    = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    kind       = Column(String(50),  nullable=False)
    title      = Column(String(200), nullable=False)
    body       = Column(String(500), nullable=True)
    link       = Column(String(255), nullable=True)
    created_at = Column(DateTime,    nullable=False)
    read_at    = Column(DateTime,    nullable=True)

    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        # newest-first listing + unread count both filter by user_id, sort by created_at
        Index("ix_notification_user_created", "user_id", "created_at"),
    )


# gold, observation list of users the detector has flagged
# one row per user, score accumulates across detection cycles
# admin can dismiss to clear the flag, dismissed rows hang around for the audit trail
class Observation(Base):
    __tablename__ = "observation"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    user_id          = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, unique=True)
    reason           = Column(String(500), nullable=False)
    score            = Column(Integer, nullable=False, default=0)
    first_flagged_at = Column(DateTime, nullable=False)
    last_flagged_at  = Column(DateTime, nullable=False)
    dismissed        = Column(Integer, nullable=False, default=0)  # 0 false, 1 true, sqlite has no bool

    user = relationship("User")


# canonical seed data, kept here so both alembic seeding and runtime startup use the same source
SUBJECT_NAMES = [
    "Matematică", "Limba Română", "Științele naturii",
    "Limba Engleză", "Istorie", "Geografie", "Educație fizică",
]

CLASS_NAMES = ["1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B"]

# roles and permissions
ROLE_ADMIN   = "admin"
ROLE_USER    = "user"
ROLE_TEACHER = "teacher"
ROLE_STUDENT = "student"
ROLE_PARENT  = "parent"

# every action a user can do is one of these codes
# admin gets all of them, every other role gets a subset
# assignment 6 added the submission + invite + parent-child permissions
PERMISSIONS = [
    "homework_read", "homework_create", "homework_update", "homework_delete",
    "student_read",  "student_create",  "student_update",  "student_delete",
    "comment_read",  "comment_create",  "comment_update",  "comment_delete",
    "stats_read",
    "chat_read",     "chat_send",
    # assignment 6
    "submission_create_own",        # student can upload their own submission
    "submission_grade_own_class",   # teacher can grade homeworks they posted
    "homework_create_own_class",    # teacher can post for class+subject they teach
    "invite_manage",                # admin generate/revoke invite codes
]

# what each role gets, kept as plain lists so seed.py can map them by code
ROLE_PERMISSIONS: dict[str, list[str]] = {
    ROLE_ADMIN: PERMISSIONS,  # admin gets everything
    ROLE_USER: [
        "homework_read", "student_read",
        "comment_read",  "comment_create",
        "stats_read",
        "chat_read",     "chat_send",
    ],
    # teacher can read+post homeworks for their assigned class+subject pairs
    # and grade the ones they posted. they cant see other teachers' homeworks.
    ROLE_TEACHER: [
        "homework_read", "homework_create_own_class", "homework_update", "homework_delete",
        "student_read",  "submission_grade_own_class",
        "comment_read",  "comment_create",
        "stats_read",
        "chat_read",     "chat_send",
    ],
    # student sees only homeworks for their class. they submit, dont grade.
    # no stats access, that hides the pie chart entirely.
    ROLE_STUDENT: [
        "homework_read",
        "submission_create_own",
        "comment_read", "comment_create",
        "chat_read",    "chat_send",
    ],
    # parent sees homeworks for their children's classes and only their child's
    # submission status + grade + feedback. no stats access either.
    ROLE_PARENT: [
        "homework_read",
        "comment_read", "comment_create",
        "chat_read",    "chat_send",
    ],
}

# the two demo accounts the lab teacher will log in as, plus the assignment 6
# trio for teacher/student/parent. seeded with relationships in seed.py
DEMO_USERS = [
    {"email": "admin@proelev.ro",   "password": "Admin123",   "name": "Admin",        "role": ROLE_ADMIN},
    {"email": "user@proelev.ro",    "password": "Parola123",  "name": "User Demo",    "role": ROLE_USER},
    {"email": "prof@proelev.ro",    "password": "Profesor1",  "name": "Prof. Demo",   "role": ROLE_TEACHER},
    {"email": "elev@proelev.ro",    "password": "Elev1234",   "name": "Elev Demo",    "role": ROLE_STUDENT},
    {"email": "parinte@proelev.ro", "password": "Parinte1",   "name": "Părinte Demo", "role": ROLE_PARENT},
]

# assignment 6 invite codes for self-register flow, in days
INVITE_CODE_TTL_DAYS = 7

# the per-class roster used when a homework is created, students are auto inserted
CLASS_ROSTER: dict[str, list[str]] = {
    "1A": ["Alexandru Popescu", "Maria Ionescu", "Andrei Constantin", "Elena Dumitrescu", "Mihai Georgescu",
           "Adrian Mocanu", "Cristina Vasile", "Daniel Stoica", "Roxana Albu", "George Pop", "Iulia Negrea"],
    "1B": ["Ana Popa", "Bogdan Stancu", "Cristina Marin", "Daniel Florea", "Ioana Nistor",
           "Mihai Calin", "Andreea Tudose", "Razvan Diaconu", "Camelia Filip", "Tudor Manole", "Diana Olaru"],
    "2A": ["Radu Bucur", "Simona Dinu", "Tudor Avram", "Valentina Nicu", "Vlad Stoica",
           "Cosmina Iliescu", "Paul Cristea", "Sergiu Enescu", "Bianca Petrescu", "Iulian Mocanu", "Stefania Calin"],
    "2B": ["Alina Barbu", "Cosmin Enache", "Diana Ghita", "Emil Matei", "Florina Oprea",
           "Robert Crisan", "Carmen Horvath", "Adrian Stancu", "Mariana Tudor", "Stefan Nedelcu", "Raluca Filip"],
    "3A": ["Gabriel Rusu", "Ioana Serban", "Ion Preda", "Laura Badea", "Liviu Dobre",
           "Marius Munteanu", "Andreea Popescu", "Cezar Ardelean", "Elena Mocanu", "Robert Cristea", "Madalina Florea"],
    "3B": ["Madalina Ciobanu", "Marius Ene", "Monica Luca", "Nicolae Stan", "Oana Tudor",
           "Paul Diaconu", "Daniela Marin", "Razvan Radu", "Mihaela Albu", "Vlad Stancu", "Andrada Nistor"],
    "4A": ["Octavian Vasile", "Paula Chiriac", "Petru Moldovan", "Raluca Draghici", "Sebastian Coman",
           "Cristian Negrea", "Roxana Stancu", "Tudor Calin", "Bianca Popa", "Florin Petrescu", "Catalina Olaru"],
    "4B": ["Silviu Apostol", "Sorina Balan", "Stefan Craciun", "Teodora Mihai", "Traian Neagu",
           "Victor Manole", "Iulia Cristea", "Andrei Filip", "Diana Mocanu", "Bogdan Enescu", "Adriana Nedelcu"],
}
