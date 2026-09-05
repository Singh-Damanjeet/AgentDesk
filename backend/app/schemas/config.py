from pydantic import BaseModel


class ConfigStatusResponse(BaseModel):
    configured: bool
    installation_id: str