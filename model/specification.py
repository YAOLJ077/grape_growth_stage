"""Immutable component definitions used by the named model folders."""
from dataclasses import dataclass

STAGES = ("07", "65", "81", "89")
DEFINITION_VERSION = "1.0.0"


@dataclass(frozen=True)
class ModelSpecification:
    name: str
    forcing: str
    chilling: str
    interaction: str
    version: str = DEFINITION_VERSION
