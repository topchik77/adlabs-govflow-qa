from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Status(StrEnum):
    DRAFT = "DRAFT"
    AWAITING_APPLICANT_SIGNATURE = "AWAITING_APPLICANT_SIGNATURE"
    SUBMITTED = "SUBMITTED"
    VALIDATING = "VALIDATING"
    UNDER_REVIEW = "UNDER_REVIEW"
    NEEDS_CORRECTION = "NEEDS_CORRECTION"
    APPROVED = "APPROVED"
    AWAITING_OFFICER_SIGNATURE = "AWAITING_OFFICER_SIGNATURE"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(StrictModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)


class Form(StrictModel):
    type: Literal["PERMIT", "RENEWAL"] = "PERMIT"
    title: str = Field(min_length=3, max_length=150)
    description: str = Field(min_length=10, max_length=4000)

    @field_validator("title", "description")
    @classmethod
    def no_controls(cls, value):
        if any(ord(c) < 32 and c not in "\n\r\t" for c in value):
            raise ValueError("Control characters are forbidden")
        return value


class VersionCommand(StrictModel):
    expected_version: int = Field(ge=1, strict=True)


class Edit(Form, VersionCommand):
    pass


class SignCommand(VersionCommand):
    document_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ReviewCommand(VersionCommand):
    decision: Literal["APPROVED", "REJECTED", "NEEDS_CORRECTION"]
    reason: str = Field(min_length=5, max_length=2000)


class UserView(BaseModel):
    id: str
    username: str
    tenant_id: str
    tenant_name: str
    role: str


class TokenView(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserView


class AttachmentView(BaseModel):
    id: str
    filename: str
    sha256: str
    mime: str
    size: int


class ApplicationView(BaseModel):
    id: str
    tenant_id: str
    applicant_id: str
    type: str
    title: str
    description: str
    business_status: Status
    processing_status: str
    version: int
    document_version: int
    document_hash: str
    decision_document: dict | None
    decision_hash: str | None
    created_at: str
    updated_at: str
    attachments: list[AttachmentView]
    applicant_signed: bool
    officer_signed: bool
    reviews: list[dict]


class PageView(BaseModel):
    items: list[ApplicationView]
    total: int
    limit: int
    offset: int


class SubmitView(BaseModel):
    application_id: str
    business_status: Status
    processing_status: str
    version: int
    correlation_id: str


class ErrorView(BaseModel):
    code: str
    message: str
    correlation_id: str
    details: dict = Field(default_factory=dict)
