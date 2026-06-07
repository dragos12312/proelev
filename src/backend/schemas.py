from pydantic import BaseModel, field_validator, model_validator
from typing import Optional
from datetime import date, datetime


# Auth
class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def email_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Email-ul nu poate fi gol")
        return v.strip()

    @field_validator("password")
    @classmethod
    def password_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Parola nu poate fi goală")
        return v


class LoginResponse(BaseModel):
    message: str
    user: dict
    access_token: str
    token_type: str = "bearer"


# silver, factor 1 returns this to ask the client to move to factor 2
class LoginFactorOneResponse(BaseModel):
    message: str
    challenge_id: str
    next: str = "email_code"


# silver, factor 2 returns this after the email code matches, asking for the
# security question as the third factor
class LoginFactorTwoResponse(BaseModel):
    message: str
    challenge_id: str
    security_question: str
    next: str = "security_question"


class VerifyEmailRequest(BaseModel):
    challenge_id: str
    code: str


class VerifyQuestionRequest(BaseModel):
    challenge_id: str
    answer: str


class ForgotRequest(BaseModel):
    email: str


class ResetRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not v or len(v) < 6:
            raise ValueError("Parola trebuie să aibă cel puțin 6 caractere")
        if not any(c.isdigit() for c in v):
            raise ValueError("Parola trebuie să conțină cel puțin o cifră")
        if not any(c.isalpha() for c in v):
            raise ValueError("Parola trebuie să conțină cel puțin o literă")
        return v


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    # silver, 3rd factor for login and recovery
    security_question: str
    security_answer:   str
    # assignment 6, optional invite code that escalates the new account into
    # the teacher / student / parent roles. without a code the user gets the
    # plain "user" role like before.
    invite_code: Optional[str] = None
    # for student: which class they're in if the code didn't preset one
    class_id:    Optional[int] = None
    # for teacher: which subject they teach if the code didn't preset one
    subject_id:  Optional[int] = None
    # for parent: emails of their children (must already be registered)
    children_emails: Optional[list[str]] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Numele nu poate fi gol")
        if len(v) > 150:
            raise ValueError("Numele nu poate depăși 150 de caractere")
        return v

    @field_validator("security_question")
    @classmethod
    def question_ok(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) < 5:
            raise ValueError("Întrebarea de securitate trebuie să aibă cel puțin 5 caractere")
        if len(v) > 255:
            raise ValueError("Întrebarea de securitate nu poate depăși 255 de caractere")
        return v

    @field_validator("security_answer")
    @classmethod
    def answer_ok(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) < 2:
            raise ValueError("Răspunsul trebuie să aibă cel puțin 2 caractere")
        if len(v) > 255:
            raise ValueError("Răspunsul nu poate depăși 255 de caractere")
        return v

    @field_validator("email")
    @classmethod
    def email_format(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if not v:
            raise ValueError("Email-ul nu poate fi gol")
        # basic shape check, the real validation is uniqueness at the db level
        if "@" not in v or "." not in v.split("@", 1)[-1]:
            raise ValueError("Email invalid")
        if len(v) > 150:
            raise ValueError("Email-ul nu poate depăși 150 de caractere")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        # mild rules so the demo isnt trivial but still student friendly
        if not v or len(v) < 6:
            raise ValueError("Parola trebuie să aibă cel puțin 6 caractere")
        if not any(c.isdigit() for c in v):
            raise ValueError("Parola trebuie să conțină cel puțin o cifră")
        if not any(c.isalpha() for c in v):
            raise ValueError("Parola trebuie să conțină cel puțin o literă")
        return v


# Homework
VALID_SUBJECTS = [
    "Matematică",
    "Limba Română",
    "Științele naturii",
    "Limba Engleză",
    "Istorie",
    "Geografie",
    "Educație fizică",
    "Limba și literatura română",
]

VALID_CLASSES = [
    "1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B"
]


class HomeworkCreate(BaseModel):
    title: str
    subject: str
    assignedClass: str
    dueDate: str
    description: Optional[str] = None
    fileName: Optional[str] = None

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Titlul nu poate fi gol")
        if len(v) > 200:
            raise ValueError("Titlul nu poate depăși 200 de caractere")
        return v

    @field_validator("subject")
    @classmethod
    def subject_valid(cls, v: str) -> str:
        if v not in VALID_SUBJECTS:
            raise ValueError(f"Materia trebuie să fie una din: {', '.join(VALID_SUBJECTS)}")
        return v

    @field_validator("assignedClass")
    @classmethod
    def class_valid(cls, v: str) -> str:
        if v not in VALID_CLASSES:
            raise ValueError(f"Clasa trebuie să fie una din: {', '.join(VALID_CLASSES)}")
        return v

    @field_validator("dueDate")
    @classmethod
    def due_date_valid(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Data limită trebuie să fie în formatul YYYY-MM-DD")
        return v

    @model_validator(mode="after")
    def description_or_file(self) -> "HomeworkCreate":
        if not (self.description or "").strip() and not self.fileName:
            raise ValueError("Trebuie să existe o descriere sau un fișier atașat")
        return self


class HomeworkUpdate(BaseModel):
    title: Optional[str] = None
    subject: Optional[str] = None
    assignedClass: Optional[str] = None
    dueDate: Optional[str] = None
    description: Optional[str] = None
    fileName: Optional[str] = None

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Titlul nu poate fi gol")
            if len(v) > 200:
                raise ValueError("Titlul nu poate depăși 200 de caractere")
        return v

    @field_validator("subject")
    @classmethod
    def subject_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_SUBJECTS:
            raise ValueError(f"Materia trebuie să fie una din: {', '.join(VALID_SUBJECTS)}")
        return v

    @field_validator("assignedClass")
    @classmethod
    def class_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_CLASSES:
            raise ValueError(f"Clasa trebuie să fie una din: {', '.join(VALID_CLASSES)}")
        return v

    @field_validator("dueDate")
    @classmethod
    def due_date_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                datetime.strptime(v, "%Y-%m-%d")
            except ValueError:
                raise ValueError("Data limită trebuie să fie în formatul YYYY-MM-DD")
        return v


class HomeworkResponse(BaseModel):
    id: int
    title: str
    subject: str
    assignedClass: str
    dueDate: str
    description: Optional[str]
    fileName: Optional[str]


class PaginatedHomeworks(BaseModel):
    items: list[HomeworkResponse]
    total: int
    page: int
    pageSize: int
    totalPages: int


# Student
class StudentCreate(BaseModel):
    name: str
    dateTime: str
    grade: Optional[int] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Numele nu poate fi gol")
        return v

    @field_validator("grade")
    @classmethod
    def grade_valid(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 10):
            raise ValueError("Nota trebuie să fie între 1 și 10")
        return v


class StudentUpdate(BaseModel):
    name: Optional[str] = None
    dateTime: Optional[str] = None
    grade: Optional[int] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Numele nu poate fi gol")
        return v

    @field_validator("grade")
    @classmethod
    def grade_valid(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 10):
            raise ValueError("Nota trebuie să fie între 1 și 10")
        return v


class StudentResponse(BaseModel):
    id: int
    homeworkId: int
    userId: Optional[int] = None
    name: str
    dateTime: str
    grade: Optional[int] = None
    # assignment 6 submission fields
    submittedAt:        Optional[str] = None
    submissionText:     Optional[str] = None
    submissionFileName: Optional[str] = None
    hasFile:            Optional[bool] = False
    feedback:           Optional[str] = None


class PaginatedStudents(BaseModel):
    items: list[StudentResponse]
    total: int
    page: int
    pageSize: int
    totalPages: int


# Statistics
class GradeDistribution(BaseModel):
    grade: str
    count: int

class HomeworkStatistics(BaseModel):
    homeworkId: int
    totalStudents: int
    passed: int
    failed: int
    ungraded: int
    averageGrade: Optional[float]
    gradeDistribution: list[GradeDistribution]


# Comment (1-to-many: a Homework has many Comments)
class CommentCreate(BaseModel):
    author: str
    text: str

    @field_validator("author")
    @classmethod
    def author_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Autorul nu poate fi gol")
        if len(v) > 100:
            raise ValueError("Autorul nu poate depăși 100 de caractere")
        return v

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Textul nu poate fi gol")
        if len(v) > 1000:
            raise ValueError("Textul nu poate depăși 1000 de caractere")
        return v


class CommentUpdate(BaseModel):
    author: Optional[str] = None
    text: Optional[str] = None

    @field_validator("author")
    @classmethod
    def author_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Autorul nu poate fi gol")
            if len(v) > 100:
                raise ValueError("Autorul nu poate depăși 100 de caractere")
        return v

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Textul nu poate fi gol")
            if len(v) > 1000:
                raise ValueError("Textul nu poate depăși 1000 de caractere")
        return v


class CommentResponse(BaseModel):
    id: int
    homeworkId: int
    author: str
    text: str
    createdAt: str


class PaginatedComments(BaseModel):
    items: list[CommentResponse]
    total: int
    page: int
    pageSize: int
    totalPages: int


class CommentStatistics(BaseModel):
    homeworkId: int
    totalComments: int
    uniqueAuthors: int
    averageTextLength: float
    topAuthor: Optional[str]
