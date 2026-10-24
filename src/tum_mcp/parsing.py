from pydantic import BaseModel, ValidationError

from tum_mcp.errors import CampusError, Code


def decode[T: BaseModel](model: type[T], payload: bytes) -> T:
    try:
        return model.model_validate_json(payload)
    except ValidationError:
        raise CampusError(
            Code.INVALID_RESPONSE, "Provider returned an unsupported response shape."
        ) from None
