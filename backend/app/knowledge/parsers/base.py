from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class ParsedSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    section: str | None = Field(default=None, max_length=1000)
    metadata: dict[str, str] = Field(default_factory=dict)


class DocumentParser(Protocol):
    def parse(self, source_path: Path) -> list[ParsedSection]:
        ...
