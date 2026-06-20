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


class GoalResponse(BaseModel):
    id: str
    title: str
    description: str | None
    created_at: str
    updated_at: str
