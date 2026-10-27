"""Lazy pinned model receipts shared by the isolated recognition backends."""

from pathlib import Path
from typing import Annotated

from filelock import FileLock
from pydantic import Field, ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_processing.runtime_spec import selected
from tum_mcp.moodle.config import private_write
from tum_mcp.settings import Frozen

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class ModelAsset(Frozen):
    path: Path
    revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    config_sha256: Digest
    weights_sha256: Digest
    supporting_sha256: dict[str, Digest] = Field(default_factory=dict)


def read_asset(receipt: Path) -> ModelAsset | None:
    try:
        asset = ModelAsset.model_validate_json(receipt.read_bytes())
    except (ValidationError, OSError):
        return None
    required = {"tokenizer.json", "vocabulary.txt"} if selected().weights == "model.bin" else set()
    if not required.issubset(asset.supporting_sha256):
        return None
    if all(
        (asset.path / file).is_file() for file in ("config.json", selected().weights, *required)
    ):
        return asset
    return None


def model(name: str) -> ModelAsset:
    from tum_mcp.lecture_processing import runtime

    if name not in selected().models:
        raise CampusError(Code.INVALID_RESPONSE, "Unknown pinned lecture model.")
    repo, revision = selected().models[name]
    root = runtime.runtime_root()
    if not runtime.python_path().is_file():
        raise CampusError(Code.ACTION_REQUIRED, "Install the optional lecture runtime first.")
    with FileLock(str(root / "models.lock"), timeout=1200):
        receipt = root / f"model-{name}.json"
        if receipt.is_file():
            try:
                ModelAsset.model_validate_json(receipt.read_bytes())
            except ValidationError:
                raise CampusError(
                    Code.INVALID_RESPONSE, "Pinned model receipt is invalid; preserved for review."
                ) from None
            existing = read_asset(receipt)
            if existing is not None and existing.revision == revision:
                return existing
        asset = ModelAsset.model_validate_json(
            runtime.call_worker("model", repo=repo, revision=revision)
        )
        if asset.revision != revision:
            raise CampusError(Code.INVALID_RESPONSE, "Pinned model revision could not be verified.")
        private_write(receipt, asset.model_dump_json().encode())
        return asset
