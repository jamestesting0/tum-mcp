#!/usr/bin/env bash
# Synthetic codec/identity fixture, never a pronunciation or learning-quality sample.
set -euo pipefail
cd "$(dirname "$0")"
ffmpeg -hide_banner -loglevel error -y -f lavfi \
  -i sine=frequency=330:duration=2:sample_rate=44100 \
  -af loudnorm=I=-16:TP=-1.5:LRA=11 -ar 44100 -ac 1 -c:a aac -b:a 128k audio.m4a
ffprobe -v error -show_entries \
  stream=codec_name,sample_rate,channels:format=duration,format_name \
  -of json audio.m4a > audio-probe.json
ffmpeg -nostdin -hide_banner -i audio.m4a \
  -af loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json -f null - 2>&1 |
  sed 's/[[:blank:]]*$//' > audio-signal.txt
