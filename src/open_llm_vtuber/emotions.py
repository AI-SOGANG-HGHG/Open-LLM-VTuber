"""Configuration for Studio's turn-level affect and expression policy."""

from __future__ import annotations

from math import isclose
from pathlib import Path
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator


VadAxis = Literal["valence", "arousal", "dominance"]
VAD_AXES = get_args(VadAxis)


class _PolicyModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", allow_inf_nan=False, frozen=True, strict=True
    )


class VadRange(_PolicyModel):
    min: float
    max: float
    initial: int | float

    @model_validator(mode="after")
    def check_initial(self) -> VadRange:
        if not self.min <= self.initial <= self.max:
            raise ValueError("VAD initial value must be within the configured range")
        return self


class VadThreshold(_PolicyModel):
    min: float | None = None
    max: float | None = None

    def accepts(self, value: float) -> bool:
        return (self.min is None or value >= self.min) and (
            self.max is None or value <= self.max
        )


class AffectBlend(_PolicyModel):
    previous: float = Field(ge=0, le=1)
    event: float = Field(ge=0, le=1)
    round_digits: int = Field(alias="roundDigits", ge=0)

    @model_validator(mode="after")
    def check_weights(self) -> AffectBlend:
        if not isclose(self.previous + self.event, 1):
            raise ValueError("Affect blend weights must add up to 1")
        return self


class Expression(_PolicyModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    hint_guidance: str | None = Field(default=None, alias="hintGuidance", min_length=1)
    event_vad: dict[VadAxis, VadThreshold] = Field(
        default_factory=dict, alias="eventVad"
    )


class AppraisalPrompt(_PolicyModel):
    affect_and_evidence: tuple[str, ...] = Field(
        alias="affectAndEvidence", min_length=1
    )
    expression_hint: str = Field(alias="expressionHint")
    vad_shape: str = Field(alias="vadShape")


def _join_prompt_list(items: list[str], conjunction: str) -> str:
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])}, {conjunction} {items[-1]}"


class EmotionPolicy(_PolicyModel):
    # Only server policy is consumed here. Inline tags still use their existing code.
    model_config = ConfigDict(extra="ignore")
    version: Literal[1]
    default_expression: str = Field(alias="defaultExpression")
    vad: dict[VadAxis, VadRange]
    blend: AffectBlend
    expressions: tuple[Expression, ...]
    appraisal_prompt: AppraisalPrompt = Field(alias="appraisalPrompt")

    @model_validator(mode="after")
    def check_policy(self) -> EmotionPolicy:
        if set(self.vad) != set(VAD_AXES):
            raise ValueError("VAD must define valence, arousal, and dominance")
        ids = {expression.id for expression in self.expressions}
        if len(ids) != len(self.expressions):
            raise ValueError("Expression IDs must be unique")
        if self.default_expression not in ids:
            raise ValueError("The default expression must be defined")
        if not any(expression.hint_guidance for expression in self.expressions):
            raise ValueError("At least one expression must provide an appraisal hint")
        for expression in self.expressions:
            if bool(expression.hint_guidance) != bool(expression.event_vad):
                raise ValueError(
                    f"{expression.id} must pair hint guidance with VAD limits"
                )
            for axis, threshold in expression.event_vad.items():
                if threshold.min is None and threshold.max is None:
                    raise ValueError(f"{expression.id}.{axis} must define a VAD limit")
                axis_range = self.vad[axis]
                minimum = axis_range.min if threshold.min is None else threshold.min
                maximum = axis_range.max if threshold.max is None else threshold.max
                if not axis_range.min <= minimum <= maximum <= axis_range.max:
                    raise ValueError(
                        f"{expression.id}.{axis} limits are outside the VAD range"
                    )
        return self

    def appraisal_guidance(self) -> str:
        hints = [
            f'"{expression.id}" {expression.hint_guidance}'
            for expression in self.expressions
            if expression.hint_guidance is not None
        ]
        axes = [
            f'"{axis}" ({self.vad[axis].min:g} to {self.vad[axis].max:g})'
            for axis in VAD_AXES
        ]
        return " ".join(
            (
                *self.appraisal_prompt.affect_and_evidence,
                self.appraisal_prompt.expression_hint.format(
                    hints=_join_prompt_list(hints, "or")
                ),
                self.appraisal_prompt.vad_shape.format(
                    vad_axes=_join_prompt_list(axes, "and")
                ),
            )
        )


_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "emotions.json"
EMOTIONS = EmotionPolicy.model_validate_json(_CONFIG_PATH.read_bytes())
APPRAISAL_EXPRESSIONS = {
    expression.id: expression
    for expression in EMOTIONS.expressions
    if expression.hint_guidance is not None
}
APPRAISAL_GUIDANCE = EMOTIONS.appraisal_guidance()
