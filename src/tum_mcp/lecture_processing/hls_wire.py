"""Parse third-party HLS parser data once at a narrow typed boundary."""

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, SecretStr


class Wire(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class Resource(Wire):
    uri: SecretStr = Field(repr=False, exclude=True)
    byterange: str | None = Field(default=None, max_length=100)


class Key(Wire):
    method: str


class Part(Resource):
    duration: FiniteFloat = Field(gt=0, le=3600)
    discontinuity: bool = False
    init_section: Resource | None = None
    gap_tag: bool | None = None


class StreamInfo(Wire):
    bandwidth: int = Field(gt=0)
    resolution: str | None = None
    audio: str | None = None


class Variant(Resource):
    stream_info: StreamInfo


class Playlist(Wire):
    is_variant: bool = False
    is_endlist: bool = False
    media_sequence: int | None = Field(default=None, ge=0)
    discontinuity_sequence: int | None = Field(default=None, ge=0)
    segments: tuple[Part, ...] = Field(default=(), max_length=10000)
    playlists: tuple[Variant, ...] = Field(default=(), max_length=100)
    keys: tuple[Key | None, ...] = Field(default=(), max_length=10000)
    session_keys: tuple[Key, ...] = Field(default=(), max_length=100)
    is_i_frames_only: bool = False
    is_images_only: bool = False
