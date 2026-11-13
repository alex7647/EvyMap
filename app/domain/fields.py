"""Описание полей метаданных (FieldDef). Схему полей задаёт пользователь в PlaceType
(для мест) и в Event.activity_fields (для активностей); значения лежат в JSON-колонке props
и проверяются на записи. Новый тип поля = новый класс с coerce() и запись в union FieldDef."""
import re
from datetime import datetime
from typing import Annotated, Any, ClassVar, Literal, Optional, Union

from pydantic import BaseModel, Field, TypeAdapter


class FieldError(ValueError):
    pass


class PropsError(Exception):
    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__(errors)


class FieldBase(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    label: str = Field(min_length=1, max_length=80)
    required: bool = False
    visible_to: Literal["public", "staff"] = "public"

    def coerce(self, value: Any) -> Any:
        raise NotImplementedError


class _Str(FieldBase):
    max_length: int = Field(200, ge=1, le=20000)
    regex: ClassVar[Optional[str]] = None
    hint: ClassVar[str] = "неверный формат"

    def coerce(self, value):
        if not isinstance(value, str):
            raise FieldError("ожидается строка")
        value = value.strip()
        if len(value) > self.max_length:
            raise FieldError(f"длиннее {self.max_length} символов")
        if self.regex and not re.fullmatch(self.regex, value):
            raise FieldError(self.hint)
        return value


class TextField(_Str):
    type: Literal["text"] = "text"


class LongTextField(_Str):
    type: Literal["longtext"] = "longtext"
    max_length: int = Field(5000, ge=1, le=20000)


class PhoneField(_Str):
    type: Literal["phone"] = "phone"
    regex: ClassVar[Optional[str]] = r"\+?[0-9][0-9 ()\-]{4,19}"
    hint: ClassVar[str] = "ожидается номер телефона"


class EmailField(_Str):
    type: Literal["email"] = "email"
    regex: ClassVar[Optional[str]] = r"[^@\s]+@[^@\s]+\.[^@\s]+"
    hint: ClassVar[str] = "ожидается e-mail"


class UrlField(_Str):
    type: Literal["url"] = "url"
    max_length: int = Field(500, ge=1, le=2000)
    regex: ClassVar[Optional[str]] = r"https?://\S+"
    hint: ClassVar[str] = "ожидается ссылка http(s)://"


class NumberField(FieldBase):
    type: Literal["number"] = "number"
    min_value: Optional[float] = None
    max_value: Optional[float] = None

    def coerce(self, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise FieldError("ожидается число")
        if self.min_value is not None and value < self.min_value:
            raise FieldError(f"меньше {self.min_value}")
        if self.max_value is not None and value > self.max_value:
            raise FieldError(f"больше {self.max_value}")
        return value


class BoolField(FieldBase):
    type: Literal["bool"] = "bool"

    def coerce(self, value):
        if not isinstance(value, bool):
            raise FieldError("ожидается true/false")
        return value


class SelectField(FieldBase):
    type: Literal["select"] = "select"
    options: list[str] = Field(min_length=1, max_length=100)

    def coerce(self, value):
        if value not in self.options:
            raise FieldError("значение не из списка")
        return value


class MultiSelectField(FieldBase):
    type: Literal["multiselect"] = "multiselect"
    options: list[str] = Field(min_length=1, max_length=100)

    def coerce(self, value):
        if not isinstance(value, list) or any(v not in self.options for v in value):
            raise FieldError("значения не из списка")
        return list(dict.fromkeys(value))


def _dt(value) -> datetime:
    if not isinstance(value, str):
        raise FieldError("ожидается дата-время ISO 8601")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise FieldError("неверная дата-время")


class DateTimeField(FieldBase):
    type: Literal["datetime"] = "datetime"

    def coerce(self, value):
        return _dt(value).isoformat()


class TimeRangeField(FieldBase):
    type: Literal["timerange"] = "timerange"

    def coerce(self, value):
        if not isinstance(value, dict) or set(value) != {"start", "end"}:
            raise FieldError("ожидается {start, end}")
        a, b = _dt(value["start"]), _dt(value["end"])
        try:
            if a > b:
                raise FieldError("начало позже конца")
        except TypeError:
            raise FieldError("смешаны даты с часовым поясом и без")
        return {"start": a.isoformat(), "end": b.isoformat()}


class ContactField(FieldBase):
    """Ссылка на контакт мероприятия (id)."""
    type: Literal["contact"] = "contact"

    def coerce(self, value):
        if isinstance(value, bool) or not isinstance(value, int):
            raise FieldError("ожидается id контакта")
        return value


FieldDef = Annotated[
    Union[TextField, LongTextField, PhoneField, EmailField, UrlField, NumberField, BoolField,
          SelectField, MultiSelectField, DateTimeField, TimeRangeField, ContactField],
    Field(discriminator="type"),
]
FIELDS = TypeAdapter(list[FieldDef])


def validate_props(fields: list[FieldBase], props: dict) -> dict:
    """Проверяет значения по схеме полей, возвращает нормализованный словарь."""
    known = {f.key: f for f in fields}
    errors: dict[str, str] = {k: "неизвестное поле" for k in props if k not in known}
    clean: dict[str, Any] = {}
    for f in fields:
        value = props.get(f.key)
        if value is None or value == "":
            if f.required:
                errors[f.key] = "обязательное поле"
            continue
        try:
            clean[f.key] = f.coerce(value)
        except FieldError as e:
            errors[f.key] = str(e)
    if errors:
        raise PropsError(errors)
    return clean


def visible_props(fields: list[FieldBase], props: dict, staff: bool) -> dict:
    """Оставляет только известные поля, доступные аудитории (public / staff)."""
    return {f.key: props[f.key] for f in fields
            if f.key in props and (staff or f.visible_to == "public")}
