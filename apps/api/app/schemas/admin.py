from pydantic import BaseModel


class AdminSettingUpdate(BaseModel):
    key: str
    value: str
