import time
from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Column, String, Text, JSON, Boolean
from sqlalchemy import or_, and_

from open_webui.internal.db import Base, JSONField, get_db
from open_webui.utils.access_control import has_access

####################
# Registry Agent DB Schema
####################


class RegistryAgent(Base):
    __tablename__ = "registry_agent"

    id = Column(String, primary_key=True)
    user_id = Column(String)  # Owner/Submitter

    url = Column(String, unique=True, nullable=False)  # A2A JSON URL
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    image_url = Column(String, nullable=True)
    foundational_model = Column(String, nullable=True)

    # Metadata extracted from A2A JSON
    tools = Column(JSONField, nullable=True)  # Summary of capabilities/skills

    # Access Control
    access_control = Column(JSON, nullable=True)
    # - `None`: Public access (visible to all users)
    # - `{}`: Private access (owner only)
    # - Custom permissions: {"read": {"group_ids": [...]}, "write": ...}

    # Original well-known card URL submitted by the user (may differ from `url`)
    card_url = Column(String, nullable=True)

    # Curation
    is_featured = Column(Boolean, default=False, nullable=False)
    # Only admins may set this. Featured agents appear in the dedicated showcase section.

    created_at = Column(BigInteger)
    updated_at = Column(BigInteger)


class RegistryAgentModel(BaseModel):
    id: str
    user_id: str
    url: str
    name: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    foundational_model: Optional[str] = None
    tools: Optional[dict] = None
    access_control: Optional[dict] = None
    card_url: Optional[str] = None
    is_featured: bool = False
    created_at: int
    updated_at: int

    model_config = ConfigDict(from_attributes=True)


####################
# Forms
####################


class SubmitRegistryAgentForm(BaseModel):
    url: str
    access_control: Optional[dict] = None
    foundational_model: Optional[str] = None
    image_url: Optional[str] = None


class UpdateRegistryAgentForm(BaseModel):
    access_control: Optional[dict] = None
    name: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    is_featured: Optional[bool] = None  # admin-only field; enforced in the router


####################
# Registry Agent Table
####################


class RegistryAgentsTable:
    def insert_new_agent(
        self,
        id: str,
        user_id: str,
        url: str,
        name: str,
        description: str,
        image_url: Optional[str] = None,
        foundational_model: Optional[str] = None,
        tools: Optional[dict] = None,
        access_control: Optional[dict] = None,
        card_url: Optional[str] = None,
    ) -> Optional[RegistryAgentModel]:
        """Insert a new agent into the registry."""
        with get_db() as db:
            agent = RegistryAgentModel(
                **{
                    "id": id,
                    "user_id": user_id,
                    "url": url,
                    "name": name,
                    "description": description,
                    "image_url": image_url,
                    "foundational_model": foundational_model,
                    "tools": tools,
                    "access_control": access_control,
                    "card_url": card_url,
                    "is_featured": False,
                    "created_at": int(time.time()),
                    "updated_at": int(time.time()),
                }
            )

            try:
                result = RegistryAgent(**agent.model_dump())
                db.add(result)
                db.commit()
                db.refresh(result)
                return RegistryAgentModel.model_validate(result) if result else None
            except Exception:
                return None

    def get_agent_by_id(self, id: str) -> Optional[RegistryAgentModel]:
        """Return a single registry agent by ID."""
        try:
            with get_db() as db:
                agent = db.query(RegistryAgent).filter_by(id=id).first()
                return RegistryAgentModel.model_validate(agent) if agent else None
        except Exception:
            return None

    def get_agents_by_user_id(
        self, user_id: str, permission: str = "read"
    ) -> List[RegistryAgentModel]:
        """Return all registry agents visible to the given user."""
        with get_db() as db:
            agents = db.query(RegistryAgent).all()

            return [
                RegistryAgentModel.model_validate(agent)
                for agent in agents
                if agent.user_id == user_id
                or has_access(user_id, permission, agent.access_control)
            ]

    def get_featured_agents(self) -> List[RegistryAgentModel]:
        """Return all featured agents that are publicly accessible (access_control is None)."""
        with get_db() as db:
            agents = (
                db.query(RegistryAgent)
                .filter(
                    RegistryAgent.is_featured == True,  # noqa: E712
                    RegistryAgent.access_control == None,  # noqa: E711
                )
                .all()
            )
            return [RegistryAgentModel.model_validate(agent) for agent in agents]

    def update_agent_by_id(
        self, id: str, updated: dict
    ) -> Optional[RegistryAgentModel]:
        """Apply a partial update to a registry agent."""
        try:
            with get_db() as db:
                agent = db.query(RegistryAgent).filter_by(id=id).first()
                if not agent:
                    return None

                updated["updated_at"] = int(time.time())

                for key, value in updated.items():
                    setattr(agent, key, value)

                db.commit()
                db.refresh(agent)
                return RegistryAgentModel.model_validate(agent)
        except Exception:
            return None

    def delete_agent_by_id(self, id: str) -> bool:
        """Hard-delete a registry agent."""
        try:
            with get_db() as db:
                agent = db.query(RegistryAgent).filter_by(id=id).first()
                if not agent:
                    return False
                db.delete(agent)
                db.commit()
                return True
        except Exception:
            return False


RegistryAgents = RegistryAgentsTable()
