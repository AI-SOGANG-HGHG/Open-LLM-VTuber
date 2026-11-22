"""Apply the Studio's public character fields to a single connection, never global config."""

from __future__ import annotations

from hashlib import sha256
from os import getenv
from typing import TYPE_CHECKING, Annotated, Literal
from uuid import UUID

from loguru import logger
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    model_validator,
)

from .agent.agent_factory import AgentFactory
from .studio_profiles import (
    BigFive,
    PersonaPreset,
    studio_behavior_rules,
    studio_presets,
)

if TYPE_CHECKING:
    from .service_context import ServiceContext
    from .studio_registry import RegisteredAgent, StudioRegistry

MemoryText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
]


class StudioPersona(BaseModel):
    """Describe the public character settings submitted during creation or editing."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    workspace_id: UUID
    character_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=30)
    description: str = Field(default="", max_length=100)
    greeting: str = Field(default="", max_length=300)
    persona: str | None = Field(default=None, min_length=1, max_length=2000)
    tone: Literal["친근한 반말", "활기찬 반말", "차분한 존댓말"] | None = None
    avatar: Literal["mao", "sogangi", "ivory-crown", "symbol"]
    exploration: int = Field(default=40, ge=0, le=100)
    memories: list[MemoryText] = Field(default_factory=list, max_length=50)
    preset_id: str | None = Field(default=None, pattern=r"^[a-z0-9_-]{1,40}$")
    traits: BigFive | None = None

    @model_validator(mode="after")
    def validate_persona(self, info: ValidationInfo) -> StudioPersona:
        """Require a known creation preset or a custom persona and tone."""
        if self.preset_id:
            if (
                not (info.context or {}).get("stored")
                and self.preset_id not in studio_presets()
            ):
                raise ValueError("Unknown Studio preset")
        elif self.persona is None or self.tone is None:
            raise ValueError("A custom Studio persona requires instructions and tone")
        return self

    @property
    def history_scope(self) -> str:
        identity = f"{self.workspace_id}:{self.character_id}".encode()
        return "studio-" + sha256(identity).hexdigest()[:32]

    def prompt(self) -> str:
        notes = "\n".join(f"- {memory}" for memory in self.memories) or "(아직 없음)"
        return (
            f"너의 이름은 {self.name}이다.\n"
            f"소개: {self.description}\n성격과 대화 지침:\n{self.persona}\n"
            f"말투: {self.tone}\n"
            f"탐색 성향 설정은 0~100 중 {self.exploration}이다. "
            "현재 게임 행동 정책에 연결된 수치라고 주장하지 마.\n"
            "다음은 사용자가 이 캐릭터에 직접 등록한 참고 메모이다. "
            "자동 검색하거나 실제로 경험한 기억이라고 꾸며내지 마.\n"
            f"<사용자_참고_메모>\n{notes}\n</사용자_참고_메모>\n"
            "답변은 기본적으로 한국어로 간결하게 해. 도구가 연결되지 않은 행동을 "
            "수행했다고 주장하지 마. 표정 태그를 쓴다면 [neutral], [joy], "
            "[anger], [surprise] 중 하나를 문장과 함께 사용해."
        )


async def apply_studio_persona(
    context: ServiceContext,
    profile: StudioPersona,
    registered: RegisteredAgent | None = None,
    registry: StudioRegistry | None = None,
) -> None:
    """Build first, commit only on success; all server credentials stay on the server."""
    if registered is not None:
        preset = PersonaPreset(
            **registered.personality.model_dump(exclude={"style"}),
            style=profile.tone or registered.personality.style,
            rules=studio_behavior_rules(),
        )
    else:
        preset = studio_presets()[profile.preset_id] if profile.preset_id else None
    character = context.character_config.model_copy(deep=True)
    character.conf_uid = (
        registered.history_scope if registered else profile.history_scope
    )
    character.conf_name = profile.name
    character.character_name = profile.name
    character.persona_prompt = (
        preset.system_prompt(profile.name) if preset else profile.prompt()
    )
    if registered and profile.persona:
        character.persona_prompt += (
            f"\n캐릭터 설정에 담긴 구체적인 대화 지침\n{profile.persona}"
        )
    agent_config = character.agent_config
    agent_config.conversation_agent_choice = "basic_memory_agent"
    agent_config.agent_settings.basic_memory_agent.use_mcpp = False
    provider = agent_config.agent_settings.basic_memory_agent.llm_provider
    llm_config = getattr(agent_config.llm_configs, provider)
    if hasattr(llm_config, "raise_on_error"):
        llm_config.raise_on_error = True
    if hasattr(llm_config, "request_timeout") and llm_config.request_timeout is None:
        llm_config.request_timeout = 45
    if hasattr(llm_config, "max_retries") and llm_config.max_retries is None:
        llm_config.max_retries = 0
    system_prompt = await context.construct_system_prompt(character.persona_prompt)
    agent = AgentFactory.create_agent(
        conversation_agent_choice=agent_config.conversation_agent_choice,
        agent_settings=agent_config.agent_settings.model_dump(),
        llm_configs=agent_config.llm_configs.model_dump(),
        system_prompt=system_prompt,
        live2d_model=context.live2d_model,
        tts_preprocessor_config=character.tts_preprocessor_config,
        character_avatar=character.avatar or "",
        system_config=context.system_config.model_dump(),
    )
    if preset:
        default_model = {
            "gemini_llm": "gemini-embedding-001",
            "openai_llm": "text-embedding-3-small",
        }.get(provider)
        runtime_args = (
            preset,
            profile.memories,
            getenv("STUDIO_EMBEDDING_MODEL", default_model),
        )
        if registered and registry:
            agent.enable_studio_runtime(
                registered.agent_id,
                *runtime_args,
                registry=registry,
                legacy_affect_id=profile.preset_id,
                persona_instructions=profile.persona,
            )
        else:
            agent.enable_studio_runtime(profile.preset_id, *runtime_args)
    old_agent = context.agent_engine
    context.character_config = character
    context.config = context.config.model_copy(update={"character_config": character})
    context.agent_engine = agent
    context.system_prompt = system_prompt
    context.history_uid = ""
    if old_agent and hasattr(old_agent, "close"):
        try:
            await old_agent.close()
        except Exception:
            logger.warning("Could not close the previous Studio agent")
