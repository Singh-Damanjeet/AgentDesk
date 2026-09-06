from pydantic import BaseModel, ConfigDict


class ConfigStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    configured: bool
    installation_id: str
