"""Expose Studio profile operations to the owning browser workspace."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from .studio_persona import StudioPersona
from .studio_profiles import studio_presets
from .studio_registry import (
    AgentNotFound,
    ProfileConflict,
    StudioRegistry,
    WORKSPACE_COOKIE,
)

WorkspaceCredential = Annotated[str, Cookie(alias=WORKSPACE_COOKIE, max_length=100)]


class ProfileEdit(BaseModel):
    """Pair a profile edit with the version the editor opened."""

    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    profile: StudioPersona


def studio_registry_router(registry: StudioRegistry) -> APIRouter:
    """Attach authenticated workspace endpoints to the Studio server."""
    router = APIRouter(prefix="/studio")

    @router.get("/workspace")
    def current_workspace(studio_workspace: WorkspaceCredential = "") -> dict | None:
        return registry.workspace(studio_workspace)

    @router.post("/workspaces/{workspace_id}", status_code=204)
    def register_workspace(
        workspace_id: UUID, request: Request, studio_workspace: WorkspaceCredential = ""
    ) -> Response:
        try:
            token = registry.register_workspace(workspace_id, studio_workspace)
        except AgentNotFound as error:
            raise HTTPException(404, "Workspace unavailable") from error
        response = Response(status_code=204)
        if token != studio_workspace:
            response.set_cookie(
                WORKSPACE_COOKIE,
                token,
                max_age=365 * 24 * 60 * 60,
                httponly=True,
                samesite="strict",
                secure=request.url.scheme == "https",
            )
        return response

    @router.get("/presets")
    def presets() -> dict:
        return {
            key: preset.model_dump(mode="json", exclude={"rules"})
            for key, preset in studio_presets().items()
        }

    @router.post("/agents")
    def create_agent(
        profile: StudioPersona, studio_workspace: WorkspaceCredential = ""
    ) -> dict:
        try:
            return registry.create(profile, studio_workspace).public()
        except AgentNotFound as error:
            raise HTTPException(404, "Workspace or agent unavailable") from error

    @router.post("/agents/import")
    def import_agent(
        profile: StudioPersona, studio_workspace: WorkspaceCredential = ""
    ) -> dict:
        try:
            return registry.create(profile, studio_workspace, legacy=True).public()
        except AgentNotFound as error:
            raise HTTPException(404, "Workspace or agent unavailable") from error

    @router.post("/agents/{source_id}/copy")
    def copy_agent(
        source_id: str,
        profile: StudioPersona,
        studio_workspace: WorkspaceCredential = "",
    ) -> dict:
        try:
            return registry.create(
                profile, studio_workspace, source_id=source_id
            ).public()
        except AgentNotFound as error:
            raise HTTPException(404, "Workspace or agent unavailable") from error

    @router.get("/workspaces/{workspace_id}/agents/{agent_id}")
    def read_agent(
        workspace_id: UUID, agent_id: str, studio_workspace: WorkspaceCredential = ""
    ) -> dict:
        try:
            return registry.get(workspace_id, studio_workspace, agent_id).public()
        except AgentNotFound as error:
            raise HTTPException(404, "Agent unavailable") from error

    @router.put("/agents/{agent_id}")
    def update_agent(
        agent_id: str, edit: ProfileEdit, studio_workspace: WorkspaceCredential = ""
    ) -> dict:
        try:
            return registry.update(
                agent_id, studio_workspace, edit.version, edit.profile
            ).public()
        except AgentNotFound as error:
            raise HTTPException(404, "Agent unavailable") from error
        except ProfileConflict as error:
            raise HTTPException(
                409, "Profile version or creation preset changed"
            ) from error

    @router.delete("/workspaces/{workspace_id}/agents/{agent_id}", status_code=204)
    def archive_agent(
        workspace_id: UUID, agent_id: str, studio_workspace: WorkspaceCredential = ""
    ) -> Response:
        try:
            registry.archive(workspace_id, studio_workspace, agent_id)
        except AgentNotFound as error:
            raise HTTPException(404, "Agent unavailable") from error
        return Response(status_code=204)

    return router
