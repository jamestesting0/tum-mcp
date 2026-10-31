#!/usr/bin/env bash
# Run after generate.py speech and video. No install-time execution.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
work="$1"
for key in referents-clear referents-dense delivery-clear delivery-broken; do
  ffmpeg -hide_banner -loglevel error -y -i "$work/$key.wav" \
    -af loudnorm=I=-16:TP=-1.5:LRA=11 -ar 44100 -c:a aac -aac_pns 0 -b:a 96k \
    "$here/$key.m4a"
  printf 'AUDIO %s\n' "$key"
done
for key in synchrony-aligned synchrony-early worked-opaque worked-clear; do
  speech="$key"
  case "$key" in synchrony-*) speech=synchrony ;; esac
  ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i "$work/$key.ffconcat" \
    -i "$work/$speech.wav" -vf fps=15,format=yuv420p -c:v libx264 -crf 30 \
    -af loudnorm=I=-16:TP=-1.5:LRA=11 -c:a aac -aac_pns 0 -b:a 96k \
    -movflags +faststart -shortest "$here/$key.mp4"
  printf 'VIDEO %s\n' "$key"
done
