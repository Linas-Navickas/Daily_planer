"""Pydantic request schemas for the planner HTTP API."""

from datetime import date, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator


TaskCategory = Literal["Darbas", "Asmeniniai", "Sveikata", "Kita"]


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(RequestModel):
    password: StrictStr


class TaskCreateRequest(RequestModel):
    date: date
    text: str = Field(min_length=1, max_length=120)
    category: TaskCategory = "Kita"
    time: str = ""
    location: str = Field(default="", max_length=200)

    @field_validator("text", mode="before")
    @classmethod
    def strip_task_text(cls, value):
        if not isinstance(value, str):
            raise ValueError("Task text must be a string.")
        return value.strip()

    @field_validator("location", mode="before")
    @classmethod
    def normalize_location(cls, value):
        if not isinstance(value, str):
            raise ValueError("Location must be a string.")
        return value.strip()

    @field_validator("time")
    @classmethod
    def validate_task_time(cls, value):
        if not value:
            return value
        try:
            parsed = time.fromisoformat(value)
        except ValueError as error:
            raise ValueError("Time must use HH:MM format.") from error
        if parsed.strftime("%H:%M") != value:
            raise ValueError("Time must use HH:MM format.")
        return value


class TaskDoneRequest(RequestModel):
    done: StrictBool


class WeightRequest(RequestModel):
    date: date
    weight: float = Field(ge=1, le=500)

    @field_validator("weight", mode="before")
    @classmethod
    def reject_boolean_weight(cls, value):
        if isinstance(value, bool):
            raise ValueError("Weight must be numeric.")
        return value


class StepsRequest(RequestModel):
    date: date
    count: StrictInt = Field(ge=0, le=200_000)


class VitalsRequest(RequestModel):
    date: date
    pulse: StrictInt = Field(ge=20, le=250)
    systolic: StrictInt = Field(ge=40, le=300)
    diastolic: StrictInt = Field(ge=20, le=200)

    @field_validator("diastolic")
    @classmethod
    def validate_pressure_order(cls, diastolic, info):
        systolic = info.data.get("systolic")
        if systolic is not None and systolic <= diastolic:
            raise ValueError("Systolic pressure must be higher than diastolic pressure.")
        return diastolic
