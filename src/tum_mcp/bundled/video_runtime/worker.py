"""Video Notes runtime worker: one JSON request on stdin, one JSON result on stdout."""

import importlib.util
import json
import shutil
import sys
import traceback
from fractions import Fraction
from pathlib import Path

FONTS = Path(__file__).with_name("fonts")
SAMPLE_RATE = 48000
TARGET_LUFS = -16.0
CEILING_DBTP = -1.5
QUALITY = {
    "draft": {"width": 854, "height": 480, "fps": 15, "crf": "28", "chapter_crf": "23"},
    "final": {"width": 1920, "height": 1080, "fps": 30, "crf": "20", "chapter_crf": "12"},
}


def health(_: dict) -> dict:
    import tempfile

    import av
    import manim
    import typst

    with tempfile.TemporaryDirectory(prefix="vnotes-health-") as folder:
        source = Path(folder) / "health.typ"
        source.write_text(
            '#set text(font: "Atkinson Hyperlegible Next")\nVideo $x^2$\n', encoding="utf-8"
        )
        svg = typst.compile(str(source), format="svg", font_paths=[str(FONTS)])
    encoders = {name: name in av.codecs_available for name in ("libx264", "aac")}
    return {
        "manim": manim.__version__,
        "av": av.__version__,
        "typst_svg_bytes": len(svg),
        "encoders": encoders,
    }


def measure(request: dict) -> dict:
    import av

    results = {}
    for name in request["files"]:
        samples, rate = 0, None
        with av.open(name) as container:
            stream = container.streams.audio[0]
            for frame in container.decode(stream):
                samples += frame.samples
                rate = frame.sample_rate
        results[name] = round(samples / rate, 4) if rate else 0.0
    return {"durations": results}


def _scene_error(error: BaseException) -> str:
    frames = [
        f"line {frame.lineno}: {frame.line}"
        for frame in traceback.extract_tb(error.__traceback__)
        if frame.filename.endswith("chapters.py")
    ]
    message = f"{type(error).__name__}: {error}"
    return message + ("\n" + "\n".join(frames[-3:]) if frames else "")


def render(request: dict) -> dict:
    run = Path(request["run"])
    chapter = request["chapter"]
    quality = QUALITY[request["quality"]]
    sys.path.insert(0, str(Path(__file__).parent))
    import vnotes
    from manim import config, tempconfig

    context = vnotes.configure(run, FONTS)
    media = Path(request["media"])
    options = {
        "media_dir": str(media),
        "video_dir": "{media_dir}/v",
        "partial_movie_dir": "{media_dir}/p/{scene_name}",
        "images_dir": "{media_dir}/i",
        "text_dir": "{media_dir}/t",
        "tex_dir": "{media_dir}/x",
        "log_dir": "{media_dir}/l",
        "pixel_width": quality["width"],
        "pixel_height": quality["height"],
        "frame_rate": quality["fps"],
        "format": "mp4",
        "video_codec": "libx264",
        "pixel_format": "yuv420p",
        "video_encoder_options": {"crf": quality["chapter_crf"], "preset": "medium"},
        "verbosity": "ERROR",
        "progress_bar": "none",
        # Manim's per-animation cache advances the clock by duration, not frames;
        # the chapter cache already reuses unchanged chapters.
        "disable_caching": True,
        "write_to_movie": None,
    }
    options = {key: value for key, value in options.items() if value is not None}
    try:
        with tempconfig(options):
            spec = importlib.util.spec_from_file_location("chapters", run / "chapters.py")
            if spec is None or spec.loader is None:
                raise vnotes.VideoNotesError("chapters.py could not be loaded.")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            scene_class = getattr(module, chapter.upper(), None)
            if scene_class is None or not issubclass(scene_class, vnotes.NotesScene):
                raise vnotes.VideoNotesError(
                    f"chapters.py needs class {chapter.upper()}(NotesScene)."
                )
            scene = scene_class()
            scene.render()
            produced = Path(scene.renderer.file_writer.final_file_path)
            frames = round(scene.time * config.frame_rate)
    except Exception as error:  # noqa: BLE001 - report every scene failure to the author
        return {"chapter": chapter, "ok": False, "error": _scene_error(error)}
    import av

    with av.open(str(produced)) as container:
        written = container.streams.video[0].frames
    if written and written != frames:
        return {
            "chapter": chapter,
            "ok": False,
            "error": f"frame accounting mismatch: file has {written}, scene clock {frames}",
        }
    target = run / "chapters" / f"{chapter}.mp4"
    target.parent.mkdir(exist_ok=True)
    shutil.copyfile(produced, target)
    return {
        "chapter": chapter,
        "ok": True,
        "frames": frames,
        "duration": round(frames / quality["fps"], 4),
        "layout": context.issues,
    }


def _k_weighted(samples):
    import numpy as np
    from scipy.signal import lfilter

    # ITU-R BS.1770-4 K-weighting coefficients for 48 kHz.
    shelf_b = [1.53512485958697, -2.69169618940638, 1.19839281085285]
    shelf_a = [1.0, -1.69065929318241, 0.73248077421585]
    high_b = [1.0, -2.0, 1.0]
    high_a = [1.0, -1.99004745483398, 0.99007225036621]
    return lfilter(high_b, high_a, lfilter(shelf_b, shelf_a, np.asarray(samples, dtype=float)))


def loudness(samples) -> float | None:
    """Integrated loudness (LUFS) with BS.1770 400 ms blocks and two-stage gating."""
    import numpy as np

    weighted = _k_weighted(samples)
    block, step = int(0.4 * SAMPLE_RATE), int(0.1 * SAMPLE_RATE)
    if len(weighted) < block:
        return None
    powers = np.array(
        [np.mean(weighted[i : i + block] ** 2) for i in range(0, len(weighted) - block + 1, step)]
    )
    with np.errstate(divide="ignore"):
        levels = -0.691 + 10 * np.log10(powers)
    gated = powers[levels > -70]
    if not len(gated):
        return None
    relative = -0.691 + 10 * np.log10(np.mean(gated)) - 10
    final = powers[(levels > -70) & (levels > relative)]
    return float(-0.691 + 10 * np.log10(np.mean(final))) if len(final) else None


def true_peak(samples) -> float:
    import numpy as np
    from scipy.signal import resample_poly

    upsampled = resample_poly(np.asarray(samples, dtype=float), 4, 1)
    peak = float(np.max(np.abs(upsampled))) if len(upsampled) else 0.0
    return -120.0 if peak <= 0 else 20 * float(np.log10(peak))


def _limit(samples, ceiling_db: float):
    import numpy as np
    from scipy.ndimage import minimum_filter1d, uniform_filter1d

    ceiling = 10 ** (ceiling_db / 20)
    window = int(0.005 * SAMPLE_RATE)
    gain = np.minimum(1.0, ceiling / np.maximum(np.abs(samples), 1e-9))
    # A minimum over +-window, averaged over a shorter window, never exceeds the needed gain.
    held = minimum_filter1d(gain, size=2 * window + 1, mode="nearest")
    return samples * uniform_filter1d(held, size=window + 1, mode="nearest")


def _narration(plan: list[dict], total: float):
    import av
    import numpy as np

    buffer = np.zeros(int(round(total * SAMPLE_RATE)) + SAMPLE_RATE, dtype=np.float64)
    for item in plan:
        resampler = av.AudioResampler(format="dbl", layout="mono", rate=SAMPLE_RATE)
        pieces = []
        with av.open(item["file"]) as container:
            for frame in container.decode(container.streams.audio[0]):
                for converted in resampler.resample(frame):
                    pieces.append(converted.to_ndarray().reshape(-1))
            for converted in resampler.resample(None):
                pieces.append(converted.to_ndarray().reshape(-1))
        audio = np.concatenate(pieces) if pieces else np.zeros(0)
        start = int(round(item["start"] * SAMPLE_RATE))
        limit = int(round(item["end"] * SAMPLE_RATE))
        audio = audio[: max(0, limit - start)]
        buffer[start : start + len(audio)] += audio
    buffer = buffer[: int(round(total * SAMPLE_RATE))]
    measured = loudness(buffer)
    if measured is None:
        raise ValueError("Narration is silent or too short to measure.")
    buffer = buffer * 10 ** ((TARGET_LUFS - measured) / 20)
    # Reserve 2 dB for reconstruction peaks observed on transient-rich speech.
    buffer = _limit(buffer, CEILING_DBTP - 2.0)
    return np.clip(buffer, -1.0, 1.0)


def assemble(request: dict) -> dict:
    import av
    import numpy as np
    from PIL import Image

    quality = QUALITY[request["quality"]]
    fps = quality["fps"]
    output = Path(request["output"])
    frames_total = sum(int(item["frames"]) for item in request["chapters"])
    total = frames_total / fps
    audio = _narration(request["audio"], total) if request["audio"] else None
    temporary = output.with_suffix(".partial.mp4")
    poster_frame = int(round(request["poster_at"] * fps))
    with av.open(str(temporary), "w", options={"movflags": "+faststart"}) as container:
        video = container.add_stream("libx264", rate=fps)
        video.width, video.height, video.pix_fmt = quality["width"], quality["height"], "yuv420p"
        video.options = {"crf": quality["crf"], "preset": "medium", "profile": "high"}
        video.codec_context.time_base = Fraction(1, fps)
        sound = None
        if audio is not None:
            sound = container.add_stream("aac", rate=SAMPLE_RATE)
            sound.layout = "mono"
            sound.bit_rate = 128000
            # Both noise tools produced decoded overshoots on synthetic speech.
            sound.options = {"aac_pns": "0", "aac_tns": "0"}
        written, sample_cursor = 0, 0
        for item in request["chapters"]:
            with av.open(item["file"]) as chapter:
                stream = chapter.streams.video[0]
                count = 0
                for frame in chapter.decode(stream):
                    if count >= int(item["frames"]):
                        break
                    image = frame.reformat(
                        width=quality["width"], height=quality["height"], format="yuv420p"
                    )
                    if written == poster_frame:
                        frame.to_image().save(request["poster"], "JPEG", quality=88)
                    image.pts = written
                    image.time_base = Fraction(1, fps)
                    for packet in video.encode(image):
                        container.mux(packet)
                    written += 1
                    count += 1
                    if sound is not None:
                        until = min(len(audio), int(round(written / fps * SAMPLE_RATE)))
                        while sample_cursor + 1024 <= until:
                            block = audio[sample_cursor : sample_cursor + 1024]
                            sample_cursor = _encode_audio(container, sound, block, sample_cursor)
                if count < int(item["frames"]):
                    raise ValueError(f"{item['file']} has {count} of {item['frames']} frames.")
        for packet in video.encode():
            container.mux(packet)
        if sound is not None:
            while sample_cursor < len(audio):
                block = audio[sample_cursor : sample_cursor + 1024]
                if len(block) < 1024:
                    block = np.pad(block, (0, 1024 - len(block)))
                sample_cursor = _encode_audio(container, sound, block, sample_cursor)
            for packet in sound.encode():
                container.mux(packet)
    if not Path(request["poster"]).is_file():
        Image.new("RGB", (quality["width"], quality["height"])).save(request["poster"], "JPEG")
    temporary.replace(output)
    return {"probe": probe({"file": str(output)})["probe"], "frames": written}


def _encode_audio(container, stream, block, cursor: int) -> int:
    import av

    frame = av.AudioFrame.from_ndarray(
        block.astype("float32").reshape(1, -1), format="flt", layout="mono"
    )
    frame.sample_rate = SAMPLE_RATE
    frame.pts = cursor
    frame.time_base = Fraction(1, SAMPLE_RATE)
    for packet in stream.encode(frame):
        container.mux(packet)
    return cursor + len(block)


def probe(request: dict) -> dict:
    import av
    import numpy as np

    path = request["file"]
    with av.open(path) as container:
        video = container.streams.video[0]
        frames = sum(1 for _ in container.decode(video))
        fps = float(video.average_rate) if video.average_rate else 0.0
        result = {
            "container": container.format.name,
            "video_codec": video.codec_context.name,
            "profile": video.codec_context.profile,
            "pix_fmt": video.codec_context.pix_fmt,
            "width": video.codec_context.width,
            "height": video.codec_context.height,
            "fps": round(fps, 4),
            "video_duration": round(frames / fps, 4) if fps else 0.0,
        }
    with av.open(path) as container:
        if container.streams.audio:
            stream = container.streams.audio[0]
            resampler = av.AudioResampler(format="dbl", layout="mono", rate=SAMPLE_RATE)
            pieces = []
            for frame in container.decode(stream):
                for converted in resampler.resample(frame):
                    pieces.append(converted.to_ndarray().reshape(-1))
            samples = np.concatenate(pieces) if pieces else np.zeros(0)
            result.update(
                audio_codec=stream.codec_context.name,
                sample_rate=stream.codec_context.sample_rate,
                channels=stream.codec_context.channels,
                audio_duration=round(len(samples) / SAMPLE_RATE, 4),
                loudness_lufs=None if (lufs := loudness(samples)) is None else round(lufs, 2),
                true_peak_dbtp=round(true_peak(samples), 2),
            )
    return {"probe": result}


def frames(request: dict) -> dict:
    import av
    from PIL import Image, ImageDraw

    times = request["times"]
    labels = request["labels"]
    thumbs = []
    with av.open(request["file"]) as container:
        stream = container.streams.video[0]
        wanted = sorted(enumerate(times), key=lambda pair: pair[1])
        captured: dict[int, Image.Image] = {}
        position = 0
        previous = None
        for frame in container.decode(stream):
            moment = float(frame.pts * stream.time_base)
            while position < len(wanted) and moment > wanted[position][1] + 1e-6:
                captured[wanted[position][0]] = previous or frame.to_image()
                position += 1
            if position >= len(wanted):
                break
            previous = frame.to_image()
        for index in range(len(times)):
            image = captured.get(index, previous)
            if image is not None:
                thumbs.append(image)
    width = 480
    if not thumbs:
        return {"sheet": None}
    height = int(thumbs[0].height * width / thumbs[0].width)
    columns = min(4, len(thumbs))
    rows = (len(thumbs) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * width, rows * (height + 28)), "#000000")
    draw = ImageDraw.Draw(sheet)
    for index, image in enumerate(thumbs):
        x, y = (index % columns) * width, (index // columns) * (height + 28)
        sheet.paste(image.resize((width, height)), (x, y + 28))
        draw.text((x + 8, y + 6), labels[index], fill="#FFFFFF")
    sheet.save(request["output"], "PNG")
    return {"sheet": request["output"], "count": len(thumbs)}


ACTIONS = {
    "health": health,
    "measure": measure,
    "render": render,
    "assemble": assemble,
    "probe": probe,
    "frames": frames,
}


def main() -> None:
    request = json.loads(sys.stdin.buffer.read(4 * 1024 * 1024))
    channel = sys.stdout
    # Scene code and libraries may print; only the result may reach the parent's JSON channel.
    sys.stdout = sys.stderr
    try:
        result = {"ok": True, **ACTIONS[request["action"]](request)}
    except Exception as error:  # noqa: BLE001 - the parent reports a typed failure
        result = {"ok": False, "error": f"{type(error).__name__}: {error}"}
    finally:
        sys.stdout = channel
    channel.write(json.dumps(result))


if __name__ == "__main__":
    main()
