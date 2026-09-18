from functools import lru_cache
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

from .model import JsonValue, Report


@lru_cache(maxsize=1)
def _load_full_validator() -> ModuleType:
    path = Path(__file__).resolve().parent.parent / "validate_gptbots_config.py"
    spec = spec_from_file_location("_gptbots_full_validator", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load validator from {path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(config: JsonValue, raw_length: int) -> Report:
    return _load_full_validator().validate(config, raw_length)


def main(arguments: list[str]) -> int:
    return _load_full_validator().main(arguments)
