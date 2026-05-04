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
    Column, Integer, String, Date, DateTime, ForeignKey, UniqueConstraint, CheckConstraint, Table, Index
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

    subject        = relationship("Subject",     back_populates="homeworks")
    assigned_class = relationship("SchoolClass", back_populates="homeworks")
    students = relationship(
        "Student", back_populates="homework",
        cascade="all, delete-orphan", passive_deletes=True,
    )
    comments = relationship(
        "Comment", back_populates="homework",
        cascade="all, delete-orphan", passive_deletes=True,
    )


# one row per student per homework, grade can be null when not yet marked
class Student(Base):
    __tablename__ = "student"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    homework_id  = Column(Integer, ForeignKey("homework.id", ondelete="CASCADE"), nullable=False)
    name         = Column(String(150), nullable=False)
    date_time    = Column(String(20), nullable=False)
    grade        = Column(Integer, nullable=True)

    __table_args__ = (
        # grade must be between 1 and 10 if present, enforced at the db level too
        CheckConstraint("grade IS NULL OR (grade >= 1 AND grade <= 10)", name="ck_student_grade_range"),
    )

    homework = relationship("Homework", back_populates="students")


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
class User(Base):
    __tablename__ = "user"

    id       = Column(Integer, primary_key=True, autoincrement=True)
    email    = Column(String(150), nullable=False, unique=True)
    password = Column(String(150), nullable=False)
    name     = Column(String(150), nullable=False)
    role_id  = Column(Integer, ForeignKey("role.id", ondelete="RESTRICT"), nullable=False)

    role = relationship("Role", back_populates="users")


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

    user = relationship("User",  foreign_keys=[user_id])
    role = relationship("Role",  foreign_keys=[role_id])

    __table_args__ = (
        # the detector queries by user and time, this index makes that O(log n)
        Index("ix_action_log_user_time", "user_id", "created_at"),
        Index("ix_action_log_created_at", "created_at"),
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
ROLE_ADMIN = "admin"
ROLE_USER  = "user"

# every action a user can do is one of these codes
# admin gets all of them, normal user gets only the read ones plus posting comments
PERMISSIONS = [
    "homework_read", "homework_create", "homework_update", "homework_delete",
    "student_read",  "student_create",  "student_update",  "student_delete",
    "comment_read",  "comment_create",  "comment_update",  "comment_delete",
    "stats_read",
    "chat_read",     "chat_send",
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
}

# the two demo accounts the lab teacher will log in as
DEMO_USERS = [
    {"email": "admin@proelev.ro", "password": "Admin123",  "name": "Admin",     "role": ROLE_ADMIN},
    {"email": "user@proelev.ro",  "password": "Parola123", "name": "User Demo", "role": ROLE_USER},
]

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
