from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class GoalCreate(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None

    @field_validator("title")
    @classmethod
    def reject_blank_title(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("title must not be empty or whitespace-only")
        return stripped


class GoalUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    description: str | None = None

    @field_validator("title")
    @classmethod
    def reject_blank_title(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("title must not be empty or whitespace-only")
        return stripped


class GoalResponse(BaseModel):
    id: str
    title: str
    description: str | None
    created_at: str
    updated_at: str


class UpdateCreate(BaseModel):
    goal_id: UUID
    content: str = Field(min_length=1, max_length=4000)
    transcript: str | None = Field(default=None, max_length=20000)

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("content must not be empty or whitespace-only")
        return stripped

    @field_validator("transcript")
    @classmethod
    def reject_blank_transcript(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        return stripped or None


class UpdateResponse(BaseModel):
    id: str
    goal_id: str
    content: str
    source: str
    created_at: str
