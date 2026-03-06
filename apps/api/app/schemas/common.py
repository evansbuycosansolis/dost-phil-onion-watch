from pydantic import BaseModel


class ApiMessage(BaseModel):
    message: str


class Pagination(BaseModel):
    total: int
    offset: int
    limit: int


class ErrorResponse(BaseModel):
    detail: str
    error_code: str | None = None
