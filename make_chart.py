"""Generate a sasa rhythm chart from an audio file.

    python make_chart.py song.mp3
    python make_chart.py song.mp3 --difficulty hard --offset -30

Onsets are detected with a spectral flux novelty curve, snapped onto the beat
grid found by librosa's tempo tracker, then spread across the four lanes by the
brightness (spectral centroid) of each hit.
"""

import argparse
import json
import os

import librosa
import numpy as np

LANE_COUNT = 4
MIXER_RATE = 44100  # must match the mixer app.py opens

# subdivisions per beat, minimum gap between notes (ms), onset strength percentile
DIFFICULTIES = {
    "easy": (1, 350, 70),
    "normal": (2, 170, 50),
    "hard": (4, 90, 30),
}
JACK_GAP = 150  # same lane twice within this many ms feels bad to hit
TARGET_ONSET_RATE = 3.5  # onsets per second to look for before thinning them down

MIN_HOLD = 400  # shorter than this is just a tap with some ring to it
MAX_HOLD = 2400  # no note should pin a finger down longer than this
HOLD_SUSTAIN = 0.65  # fraction of the hit's loudness the sound must keep to count as sustained
HOLD_TAIL_GAP = 80  # leave this much room before the next note


def snap_to_grid(onsets, beats, subdivision):
    """Snap each onset time onto the beat grid, dropping ones that land too far off."""
    if len(beats) < 2:
        return onsets

    grid = []
    for start, end in zip(beats[:-1], beats[1:]):
        for i in range(subdivision):
            grid.append(start + (end - start) * i / subdivision)
    grid.append(beats[-1])
    grid = np.array(grid)

    step = np.median(np.diff(grid))
    snapped = []
    for onset in onsets:
        nearest = grid[np.argmin(np.abs(grid - onset))]
        if abs(nearest - onset) <= step * 0.5:
            snapped.append(nearest)
    return np.array(sorted(set(snapped)))


def load_audio(path, sr):
    """Decode through the same path the game plays through, resampled for analysis.

    SDL's MP3 decode runs about 0.13% shorter than librosa's, which is 200 ms of
    drift by the end of a two-and-a-half minute song -- wider than the hit window.
    Analysing what actually gets played keeps the chart aligned by construction.
    """
    try:
        import pygame
        pygame.mixer.init(MIXER_RATE, -16, 2, 512)
        y = pygame.sndarray.array(pygame.mixer.Sound(path)).astype(np.float32)
        pygame.mixer.quit()
        if y.ndim > 1:
            y = y.mean(axis=1)
        y /= np.max(np.abs(y)) or 1
        return librosa.resample(y, orig_sr=MIXER_RATE, target_sr=sr)
    except Exception as e:
        print(f"  playback decode unavailable ({e}), falling back to librosa")
        return librosa.load(path, sr=sr, mono=True)[0]


def detect_onsets(onset_env, sr, duration):
    """Find onsets, loosening the peak threshold until the song yields enough of them.

    A fixed threshold starves songs with soft or blended transients, so the rate
    the song actually produces is what decides how sensitive to be.
    """
    for delta in (0.07, 0.05, 0.04, 0.03, 0.02):
        frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr,
                                            backtrack=False, delta=delta)
        if len(frames) / duration >= TARGET_ONSET_RATE:
            break
    print(f"  onset threshold {delta} -> {len(frames)} onsets ({len(frames)/duration:.1f}/s)")
    return frames


def find_holds(times, y, sr, beat_ms):
    """Turn notes whose sound rings out into long notes, returning a length in ms each."""
    rms = librosa.feature.rms(y=y)[0]
    frame_time = librosa.frames_to_time(1, sr=sr)
    # A hit in a quiet passage clears its own low threshold trivially, so gate on the song.
    floor = np.median(rms)
    step = beat_ms / 2
    lengths = []

    for i, start in enumerate(times):
        limit = times[i + 1] - HOLD_TAIL_GAP / 1000 if i + 1 < len(times) else len(y) / sr
        peak = rms[min(int(start / frame_time), len(rms) - 1)]
        if peak < floor:
            lengths.append(0)
            continue

        # Walk forward while the sound stays loud enough to feel like one held note.
        end = start
        frame = int(start / frame_time)
        while end < limit and frame < len(rms) and rms[frame] >= peak * HOLD_SUSTAIN:
            frame += 1
            end = frame * frame_time

        length = (min(end, limit) - start) * 1000
        # Land the tail on the beat grid, and never past the next note.
        length = round(length / step) * step
        length = min(length, MAX_HOLD, (limit - start) * 1000)
        lengths.append(int(length) if length >= MIN_HOLD else 0)
    return lengths


def assign_lanes(times, brightness):
    """Map brightness to a lane, then nudge notes that would repeat a lane too soon."""
    if len(times) == 0:
        return []

    # Rank each hit against the song's own brightness range so all lanes get used.
    edges = np.quantile(brightness, [0.25, 0.5, 0.75])
    lanes = np.digitize(brightness, edges).tolist()

    for i in range(1, len(lanes)):
        gap = (times[i] - times[i - 1]) * 1000
        if lanes[i] == lanes[i - 1] and gap < JACK_GAP:
            options = [l for l in range(LANE_COUNT) if l != lanes[i - 1]]
            lanes[i] = min(options, key=lambda l: abs(l - lanes[i]))
    return lanes


def make_chart(path, difficulty, offset, lead_in, holds=True):
    subdivision, min_gap, percentile = DIFFICULTIES[difficulty]

    print(f"loading {path} ...")
    sr = 22050
    y = load_audio(path, sr)
    duration = len(y) / sr

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo, beats = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, units="time")
    tempo = float(np.atleast_1d(tempo)[0])
    print(f"  {duration:.1f}s, tempo {tempo:.1f} BPM, {len(beats)} beats")

    onset_frames = detect_onsets(onset_env, sr, duration)
    onset_times = librosa.frames_to_time(onset_frames, sr=sr)
    strength = onset_env[onset_frames]

    # Keep only the stronger hits; quiet difficulties keep fewer.
    keep = strength >= np.percentile(strength, percentile)
    onset_times = onset_times[keep]

    times = snap_to_grid(onset_times, beats, subdivision)
    print(f"  {len(times)} notes after grid snap ({subdivision}/beat)")

    # Enforce the minimum gap so the chart stays playable.
    spaced = []
    for t in times:
        if not spaced or (t - spaced[-1]) * 1000 >= min_gap:
            spaced.append(t)
    times = np.array(spaced)

    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    frames = librosa.time_to_frames(times, sr=sr)
    brightness = centroid[np.clip(frames, 0, len(centroid) - 1)]
    lanes = assign_lanes(times, brightness)

    if holds:
        lengths = find_holds(times, y, sr, 60000 / tempo)
        print(f"  {sum(1 for l in lengths if l)} long notes")
    else:
        lengths = [0] * len(times)

    note_ms = [int(round(t * 1000)) + lead_in for t in times]
    return {
        "audio": os.path.basename(path),
        "bpm": round(tempo, 2),
        "offset": offset,
        "lead_in": lead_in,
        "note": [int(l) + 1 for l in lanes],
        "time": note_ms,
        "len": lengths,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate a sasa chart from audio.")
    parser.add_argument("audio", help="path to the song (mp3/wav/ogg/flac)")
    parser.add_argument("-d", "--difficulty", choices=DIFFICULTIES, default="normal")
    parser.add_argument("-o", "--output", default="game.json")
    parser.add_argument("--offset", type=int, default=0,
                        help="ms to shift judgement if the song feels early/late")
    parser.add_argument("--lead-in", type=int, default=2000,
                        help="silent ms before the first note")
    parser.add_argument("--no-holds", dest="holds", action="store_false",
                        help="make every note a tap")
    args = parser.parse_args()

    chart = make_chart(args.audio, args.difficulty, args.offset, args.lead_in, args.holds)
    with open(args.output, "w", encoding="utf-8") as file:
        json.dump(chart, file, indent=4)

    density = len(chart["note"]) / (max(chart["time"]) / 1000) if chart["time"] else 0
    holds = sum(1 for l in chart["len"] if l)
    print(f"wrote {args.output}: {len(chart['note'])} notes ({holds} long), {density:.1f} notes/sec")


if __name__ == "__main__":
    main()
