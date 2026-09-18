"""请求体模型与字段清洗。"""
from datetime import datetime

from pydantic import BaseModel, field_validator


class SampleCreate(BaseModel):
    code: str
    name: str
    description: str | None = None

    @field_validator("code", "name")
    @classmethod
    def strip_required(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("不能为空")
        return v

    @field_validator("description")
    @classmethod
    def strip_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class EventCreate(BaseModel):
    occurred_at: datetime
    from_party: str
    to_party: str
    location: str | None = None
    note: str | None = None

    @field_validator("from_party", "to_party")
    @classmethod
    def strip_required(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("经手人/机构不能为空")
        return v

    @field_validator("location", "note")
    @classmethod
    def strip_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None

    def naive_iso(self) -> str:
        """统一存为不带时区的 ISO 字符串，保证字典序与时间序一致。"""
        dt = self.occurred_at
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt.isoformat(timespec="minutes")
