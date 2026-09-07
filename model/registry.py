"""Explicit model lookup, including folder names containing hyphens."""
from functools import lru_cache
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from .specification import ModelSpecification

MODEL_NAMES = ("FL", "FB", "CL-FL-S", "CL-FL-P", "CB-FL-S", "CB-FL-P",
               "CL-FB-S", "CL-FB-P", "CB-FB-S", "CB-FB-P")


def list_models() -> tuple[str, ...]:
    return MODEL_NAMES


@lru_cache(maxsize=10)
def get_model(name: str) -> ModelSpecification:
    if name not in MODEL_NAMES:
        raise ValueError(f"Unknown process model {name!r}; choose from {MODEL_NAMES}")
    path = Path(__file__).parent / name / "model.py"
    module_spec = spec_from_file_location(f"model._{name.replace('-', '_')}", path)
    module = module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    definition = module.MODEL
    if not isinstance(definition, ModelSpecification) or definition.name != name:
        raise ValueError(f"Invalid model definition in {path}")
    return definition
