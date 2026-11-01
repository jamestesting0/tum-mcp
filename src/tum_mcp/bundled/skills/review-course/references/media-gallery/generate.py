"""Recreate synthetic calibration assets with existing local runtimes, never at install.

Run `speech` in the existing kokoro-onnx runtime, supplying model/voices/espeak paths.
Then run `video` in the development environment (Pillow) and encode.sh.
Pass an external --work directory; only encode.sh writes final assets here.
"""

import argparse
import json
import wave
from pathlib import Path

SCRIPTS = {
    "referents-clear": [
        "Conditional probability restricts the sample space.",
        "In a fair die, the even outcomes are two, four, and six.",
        "Among these three even outcomes, only six is greater than four.",
        "The conditional probability is one out of three.",
    ],
    "referents-dense": [
        "Conditioning restricts the space to the second set.",
        "It has three, and only the last is in the first one.",
        "Divide that by this, giving one third.",
    ],
    "delivery-clear": [
        "An empty queue does not contain an item.",
        "Check that the queue is not empty before removing its first item.",
    ],
    "delivery-broken": [
        "An empty queue does contain an item.",
        "Check that the queue is empty before removing its first item.",
    ],
    "synchrony": [
        "A fair die has six equally likely outcomes.",
        "Condition on even outcomes: retain two, four, and six.",
        "Of those three outcomes, only six exceeds four.",
        "So the conditional probability is one third.",
    ],
    "worked-opaque": [
        "Solve two x plus three equals eleven.",
        "Apply the formula. The answer is x equals four.",
    ],
    "worked-clear": [
        "Solve two x plus three equals eleven.",
        "Subtract three from both sides to preserve equality: two x equals eight.",
        "Divide both sides by two. Each equal group has four, so x equals four.",
        "Substitute four: two times four plus three equals eleven. The result checks.",
    ],
}


def speech(args: argparse.Namespace) -> None:
    import numpy as np
    from kokoro_onnx import EspeakConfig, Kokoro

    engine = Kokoro(args.model, args.voices, espeak_config=EspeakConfig(data_path=args.espeak))
    durations = {}
    for key, sentences in SCRIPTS.items():
        blocks, ends = [], []
        for sentence in sentences:
            samples, rate = engine.create(sentence, voice="af_heart", speed=1, lang="en-us")
            blocks.append(np.concatenate((samples, np.zeros(int(rate * 0.35)))))
            ends.append(sum(len(block) for block in blocks) / rate)
        audio = (np.concatenate(blocks).clip(-1, 1) * 32767).astype("<i2")
        path = args.work / f"{key}.wav"
        with wave.open(str(path), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(rate)
            stream.writeframes(audio.tobytes())
        durations[key] = ends
        print(f"SPEECH {key} {ends[-1]:.3f}s", flush=True)
    (args.work / "timing.json").write_text(json.dumps(durations), encoding="utf-8")


def video(args: argparse.Namespace) -> None:
    from PIL import Image, ImageDraw, ImageFont

    timing = json.loads((args.work / "timing.json").read_bytes())
    font = ImageFont.truetype(args.font, 52)
    small = ImageFont.truetype(args.font, 44)
    for key in ("synchrony-aligned", "synchrony-early", "worked-opaque", "worked-clear"):
        speech_key = "synchrony" if key.startswith("synchrony") else key
        ends = timing[speech_key]
        phases = []
        for index, end in enumerate(ends):
            image = Image.new("RGB", (1280, 720), "#ffffff")
            draw = ImageDraw.Draw(image)
            worked = key.startswith("worked")
            draw.text(
                (60, 42),
                "Solve for x" if worked else "P(outcome > 4 | even)",
                font=font,
                fill="#072140",
            )
            if worked:
                rows = [
                    "2x + 3 = 11",
                    "2x = 8     subtract 3 both sides",
                    "x = 4       divide both sides by 2",
                    "Check: 2(4) + 3 = 11",
                ]
                visible = [rows[0], "x = 4"] if key.endswith("opaque") else rows[: index + 1]
                for row, text in enumerate(visible):
                    draw.text((100, 145 + row * 68), text, font=font, fill="#072140")
                if not key.endswith("opaque") and index >= 2:
                    for group in range(2):
                        x = 120 + group * 280
                        draw.rectangle((x, 470, x + 220, 550), outline="#3070b3", width=4)
                        draw.text((x + 75, 485), "4", font=font, fill="#3070b3")
                    draw.text((720, 490), "two equal groups = 8", font=small, fill="#072140")
            else:
                phase = 3 if key.endswith("early") else index
                for value in range(1, 7):
                    x = 75 + (value - 1) * 190
                    retained = phase == 0 or value % 2 == 0
                    draw.rectangle(
                        (x, 190, x + 145, 310),
                        fill="#eaf2fa" if retained else "#ffffff",
                        outline="#3070b3" if retained else "#526477",
                        width=4,
                    )
                    draw.text((x + 55, 225), str(value), font=font, fill="#072140")
                    if phase >= 2 and value == 6:
                        draw.ellipse((x + 30, 210, x + 118, 300), outline="#3070b3", width=4)
                if phase >= 1:
                    draw.text(
                        (85, 370), "Condition: even  ->  {2, 4, 6}", font=font, fill="#072140"
                    )
                if phase >= 3:
                    draw.text(
                        (85, 460), "1 favorable / 3 retained = 1/3", font=font, fill="#3070b3"
                    )
            # A caption band remains clear; caption text is a separate measured asset.
            frame = args.work / f"{key}-{index}.png"
            image.save(frame)
            start = ends[index - 1] if index else 0
            phases.extend([f"file '{frame.as_posix()}'", f"duration {end - start}"])
        phases.append(f"file '{frame.as_posix()}'")
        listing = args.work / f"{key}.ffconcat"
        listing.write_text("\n".join(phases) + "\n", encoding="utf-8")
        print(f"FRAMES {key} {ends[-1]:.3f}s", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("speech", "video"))
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--model")
    parser.add_argument("--voices")
    parser.add_argument("--espeak")
    parser.add_argument("--font")
    options = parser.parse_args()
    options.work = options.work.resolve()
    options.work.mkdir(parents=True, exist_ok=True)
    (speech if options.mode == "speech" else video)(options)
