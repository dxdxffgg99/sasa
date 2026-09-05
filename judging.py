"""Timing score, judgement thresholds, and the post-song offset/drift advice."""
import math

import config as c


def judge_score(error):
    """Score(dt): a Gaussian centered on Sync, asymmetric between early/late hits."""
    diff = error - c.SYNC
    sigma = c.SIGMA_EARLY if diff < 0 else c.SIGMA_LATE
    return math.exp(-c.SCORE_P * diff ** 2 / (2 * sigma ** 2))


def rate(error):
    s = judge_score(error)
    if s >= c.THRESHOLD_MARVELOUS:
        return "MARVELOUS"
    elif s >= c.THRESHOLD_PERFECT:
        return "PERFECT"
    elif s >= c.THRESHOLD_GREAT:
        return "GREAT"
    elif s >= c.THRESHOLD_GOOD:
        return "GOOD"
    return "MISS"


def median(values):
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def measure_drift(hits):
    """Fractional drift between chart and song, from how the error grows.

    A constant lateness is just an offset. Error that *grows* through the song
    means the two timelines run at different speeds -- almost always the mixer
    resampling the song to a rate it was not encoded at. Comparing the median
    error of the first half against the second half gives the slope without
    letting a few fumbled notes tilt it.
    """
    if len(hits) < c.MIN_HITS_FOR_DRIFT:
        return None
    half = len(hits) // 2
    early, late = hits[:half], hits[half:]
    span = median([t for t, _ in late]) - median([t for t, _ in early])
    if span <= 0:
        return None
    return (median([e for _, e in late]) - median([e for _, e in early])) / span


def offset_advice(hits, sync_offset, song_ms):
    """What the player's own timing says about the chart's alignment."""
    if len(hits) < 10:
        return ["10노트 이상 쳐야 오프셋을 추천할 수 있어요"]

    errors = [error for _, error in hits]
    middle = median(errors)
    average = sum(errors) / len(errors)
    print(f"hits: {len(errors)}  median error: {middle:+d} ms  average: {average:+.1f} ms")
    print(f"suggested offset: {sync_offset - middle} (currently {sync_offset})")
    print("positive error means you pressed late, so the notes were arriving early")
    lines = [
        f"판정 오차 중앙값 {middle:+d} ms (평균 {average:+.1f} ms)",
        f"추천 offset: {sync_offset - middle}  (현재 {sync_offset})",
    ]

    drift = measure_drift(hits)
    if drift is not None and abs(drift) > c.DRIFT_WARN:
        total = drift * song_ms
        print(f"drift: {drift * 100:+.3f}% ({total:+.0f} ms across the song)")
        lines.append(f"곡이 갈수록 {drift * 100:+.3f}% 밀림 (끝까지 {total:+.0f} ms)")
        lines.append("offset으로는 못 고쳐요 — 믹서 샘플레이트가 곡과 다릅니다")
    return lines
