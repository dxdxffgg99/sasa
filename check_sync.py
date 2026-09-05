"""Measure how well a chart lines up with its song, without playing it.

Scores a chart by how much onset energy sits under its notes, then sweeps a
constant shift and a time scale to find the alignment that scores best. A shift
means the chart needs an `offset:`; a scale away from 1.0 means the chart and
the song run at different speeds, which `offset:` cannot fix -- that is the
mixer resampling the song, and the cure is `sample_rate:`.

    python check_sync.py R.dx
    python check_sync.py R.dx --rates 44100 48000
"""

import argparse
import sys

import numpy as np

import audio
import dx

HOP_MS = 5.0
FFT_SIZE = 1024
SCALES = np.linspace(0.997, 1.003, 121)
# Onset alignment repeats every half beat -- music is periodic, so a chart shifted
# a half beat scores just as well as one shifted not at all. Only shifts smaller
# than a quarter beat are unambiguous; anything larger is a rhythmic change, not
# a sync fix, so the search refuses to go there.
MAX_SHIFT_BEATS = 0.25
SHIFT_CLAMP_MS = (40, 250)


def decode(path, rate):
    """The song as the mixer would hand it to the speakers at `rate`."""
    import pygame
    pygame.mixer.init(rate, -16, 2, 512)
    got = pygame.mixer.get_init()[0]
    y = pygame.sndarray.array(pygame.mixer.Sound(path)).astype(np.float32)
    pygame.mixer.quit()
    if y.ndim > 1:
        y = y.mean(axis=1)
    return y / (np.max(np.abs(y)) or 1), got


def onset_envelope(y, rate):
    """Spectral flux: how much louder each frequency band got since last frame."""
    hop = max(1, int(rate * HOP_MS / 1000))
    frames = 1 + (len(y) - FFT_SIZE) // hop
    window = np.hanning(FFT_SIZE).astype(np.float32)
    strides = (y.strides[0] * hop, y.strides[0])
    blocks = np.lib.stride_tricks.as_strided(y, (frames, FFT_SIZE), strides)
    spectrum = np.abs(np.fft.rfft(blocks * window, axis=1))
    spectrum = np.log1p(spectrum * 10)
    flux = np.diff(spectrum, axis=0).clip(min=0).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    return (flux - flux.mean()) / (flux.std() or 1), hop


def score(envelope, hop, rate, times_ms, shift_ms, scale):
    """Mean onset strength under the notes, for one shift and time scale."""
    frame = (np.asarray(times_ms) * scale + shift_ms) * rate / 1000 / hop
    frame = np.rint(frame).astype(int)
    inside = frame[(frame >= 0) & (frame < len(envelope))]
    return float(envelope[inside].mean()) if len(inside) else -9e9


def align(chart, rate, verbose=True):
    """Best shift and time scale for this chart against the song at `rate`."""
    y, got = decode(chart["audio"], rate)
    envelope, hop = onset_envelope(y, got)
    # Where each note lands in the song as the game will judge it: the game hits
    # a note when music_pos + lead_in + offset reaches its time, so an offset the
    # chart already carries has to come out here or a fixed chart still reads bad.
    times = [t - chart["lead_in"] - chart["offset"] for t in chart["time"]]
    beat_ms = 60000 / (chart["bpm"] or 120)
    limit = min(max(beat_ms * MAX_SHIFT_BEATS, SHIFT_CLAMP_MS[0]), SHIFT_CLAMP_MS[1])
    # Step out from zero rather than up from -limit, so "no change at all" is
    # always one of the candidates and the search can never score below it.
    steps = int(limit // HOP_MS)
    shifts = np.arange(-steps, steps + 1) * HOP_MS

    grid = [(score(envelope, hop, got, times, shift, scale), shift, scale)
            for scale in SCALES for shift in shifts]
    best = max(grid, key=lambda item: item[0])
    plain = score(envelope, hop, got, times, 0, 1.0)
    # How far the shift can move before the score drops off tells us whether the
    # peak is sharp enough to trust. A flat chart gives a wide, weak answer.
    near = [shift for value, shift, _ in grid if value >= best[0] * 0.9]
    band = (min(near), max(near)) if near else (best[1], best[1])
    # Control: the same number of notes scattered at random. The metric only
    # means something if a real chart beats this by a wide margin.
    rng = np.random.default_rng(0)
    control = float(np.mean([
        score(envelope, hop, got, rng.uniform(0, max(times), len(times)), 0, 1.0)
        for _ in range(20)]))
    result = dict(rate=got, plain=plain, best=best[0], shift=best[1], scale=best[2],
                  control=control, span=max(times), band=band)
    if verbose:
        print(f"  믹서 {got:>5} Hz | 그대로 {plain:+.3f} | 최적 {best[0]:+.3f} "
              f"@ shift {best[1]:+.0f} ms, scale {best[2]:.5f} "
              f"(곡 끝 {(best[2] - 1) * max(times):+.0f} ms) | 무작위 대조 {control:+.3f}")
        print(f"        shift 신뢰구간 {band[0]:+.0f} ~ {band[1]:+.0f} ms "
              f"(최고점의 90% 이상인 범위)")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("chart")
    parser.add_argument("--rates", type=int, nargs="*",
                        help="mixer rates to try (default: the chart's and the song's)")
    args = parser.parse_args()

    chart = dx.load(args.chart)
    if not chart["audio"]:
        print(f"{args.chart}: no audio to check against")
        return 1

    native = audio.native_rate(chart["audio"])
    rates = args.rates or sorted({chart["sample_rate"] or 44100, native or 44100, 44100})
    beat_ms = 60000 / (chart["bpm"] or 120)
    limit = min(max(beat_ms * MAX_SHIFT_BEATS, SHIFT_CLAMP_MS[0]), SHIFT_CLAMP_MS[1])
    print(f"{args.chart}: {len(chart['note'])} notes, 음원 원본 {native} Hz, "
          f"헤더 sample_rate {chart['sample_rate'] or '없음'}")
    print(f"  (1박 {beat_ms:.0f} ms, shift 탐색 범위 +-{limit:.0f} ms — "
          f"그보다 큰 보정은 반박자 밀기와 구분되지 않습니다)")

    results = [align(chart, rate) for rate in rates]

    # The timeline a chart was built in shows up as the scale that fits best,
    # not the shift: a constant offset ruins the score at every rate equally.
    winner = min(results, key=lambda r: abs(r["scale"] - 1))
    drift = (winner["scale"] - 1) * winner["span"]
    print()
    if winner["best"] < winner["control"] + 0.5:
        print("  -> 이 채보는 어느 쪽으로도 음원과 맞지 않습니다 (무작위와 비슷한 점수)")
        return 1
    print(f"  -> 이 채보는 {winner['rate']} Hz 믹서 기준으로 만들어졌습니다 "
          f"(그 위에서 scale {winner['scale']:.5f}, 즉 배속 어긋남 없음)")
    print(f"     sample_rate: {winner['rate']}  를 헤더에 넣으세요")
    low, high = winner["band"]
    if low <= 0 <= high:
        print(f"     offset {chart['offset']} 은 신뢰구간 안에 있습니다 — 그대로 두세요")
    elif abs(winner["shift"]) >= HOP_MS:
        print(f"     offset: {int(round(chart['offset'] - winner['shift']))}  "
              f"를 넣으면 판정이 맞습니다 (현재 {chart['offset']})")
    else:
        print(f"     offset {chart['offset']} 은 이미 맞습니다")
    if high - low > 60:
        print(f"     (봉우리가 평평해서 offset 추정은 참고만 하세요)")
    if abs(drift) > 40:
        print(f"     그 위에서도 곡 끝까지 {drift:+.0f} ms 가 남습니다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
