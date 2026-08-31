from pydantic import BaseModel, Field, ValidationError

from app.core.errors import RuleViolation, validation_error_to_envelope


class Sample(BaseModel):
    amount: str = Field(min_length=1)
    title: str


def test_rule_violation_carries_field():
    e = RuleViolation("Сумма должна быть больше нуля", field="amount")
    assert e.message == "Сумма должна быть больше нуля"
    assert e.field == "amount"


def test_rule_violation_without_field():
    assert RuleViolation("Так нельзя").field is None


def test_validation_error_maps_to_single_message():
    # Наружу уходит одна ошибка, а не список: форма показывает одно
    # сообщение, и выбирать из пяти пришлось бы клиенту.
    try:
        Sample(amount="", title="x")
    except ValidationError as exc:
        envelope = validation_error_to_envelope(exc)
    assert envelope["field"] == "amount"
    assert envelope["error"]


def test_missing_field_reports_its_name():
    try:
        Sample(amount="10")
    except ValidationError as exc:
        envelope = validation_error_to_envelope(exc)
    assert envelope["field"] == "title"
