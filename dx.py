"""The sasa chart format (.dx): reader, writer, and a cheap header scanner.

A .dx file is UTF-8 text in two parts -- a header of `key: value` lines, then
the notes:

    title: Pixelation
    audio: pixelation.mp3
    bpm: 129.2
    lead_in: 2000

    [notes]
    # when      lanes   hold
    2116        1
    4:1         2,4
    4:1.5       3       1b

Times count from the first sample of the song, so a chart never has to know
about the silent lead-in -- `load` adds it. A time is either milliseconds
(`2116`) or a `measure:beat` spot on the bpm grid (`4:1.5`), both counting from
1, so `1:1` is the downbeat the song opens on. Lanes are 1-4 and a comma joins
the ones hit together. The third column, if present, holds the note down that
long: milliseconds, or beats with a `b` after them.

Everything after `#` is a comment, and blank lines are free.
"""

import os

LANE_COUNT = 4

DEFAULTS = {
    "title": "",
    "artist": "",
    "audio": None,
    "bpm": 120.0,
    "offset": 0,
    "lead_in": 2000,
    "difficulty": "",
    "level": 0,
    "beats_per_measure": 4,
}
# Header keys are typo-checked against this, so a misspelling fails loudly
# instead of silently charting at the default tempo.
HEADER_TYPES = {
    "title": str,
    "artist": str,
    "audio": str,
    "bpm": float,
    "offset": int,
    "lead_in": int,
    "difficulty": str,
    "level": int,
    "beats_per_measure": int,
}


class DxError(Exception):
    """A .dx file that could not be read, always naming the offending line."""


def _fail(path, lineno, message):
    raise DxError(f"{os.path.basename(path)}:{lineno}: {message}")


def _strip_comment(line):
    return line.split("#", 1)[0].strip()


def _parse_time(token, path, lineno, bpm, bpm_given, beats_per_measure):
    """Milliseconds from the start of the song, from either notation."""
    if ":" not in token:
        try:
            return float(token)
        except ValueError:
            _fail(path, lineno, f"bad time {token!r}: want milliseconds or measure:beat")

    if not bpm_given:
        _fail(path, lineno, f"measure:beat time {token!r} needs a bpm in the header")

    measure, _, beat = token.partition(":")
    try:
        measure, beat = int(measure), float(beat)
    except ValueError:
        _fail(path, lineno, f"bad measure:beat {token!r}")
    if measure < 1 or beat < 1:
        _fail(path, lineno, f"{token!r}: measures and beats count from 1")
    beats = (measure - 1) * beats_per_measure + (beat - 1)
    return beats * 60000.0 / bpm


def _parse_lanes(token, path, lineno):
    lanes = []
    for part in token.split(","):
        try:
            lane = int(part)
        except ValueError:
            _fail(path, lineno, f"bad lane {part!r}: want 1-{LANE_COUNT}")
        if not 1 <= lane <= LANE_COUNT:
            _fail(path, lineno, f"lane {lane} is outside 1-{LANE_COUNT}")
        lanes.append(lane)
    if len(set(lanes)) != len(lanes):
        _fail(path, lineno, f"lane repeated in {token!r}")
    return lanes


def _parse_hold(token, path, lineno, bpm):
    """Hold length in ms; `500` is milliseconds and `2b` is two beats."""
    if token in ("-", "0", ""):
        return 0.0
    beats = token.endswith("b")
    try:
        value = float(token[:-1] if beats else token)
    except ValueError:
        _fail(path, lineno, f"bad hold length {token!r}: want milliseconds or beats (e.g. 1.5b)")
    if value < 0:
        _fail(path, lineno, f"negative hold length {token!r}")
    return value * 60000.0 / bpm if beats else value


def loads(text, path="<string>"):
    """Parse .dx text into a chart dict. Raises DxError with a line number."""
    chart = dict(DEFAULTS)
    bpm_given = False
    in_notes = False
    hits = []  # (time_ms, lane, hold_ms)

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = _strip_comment(raw)
        if not line:
            continue

        if line.lower() == "[notes]":
            in_notes = True
            continue

        # The header runs until the first line that is not `key: value`, so the
        # [notes] marker is a courtesy rather than a requirement.
        if not in_notes and ":" in line and not line.split(":", 1)[0].strip().isdigit():
            key, _, value = line.partition(":")
            key, value = key.strip().lower(), value.strip()
            if key not in HEADER_TYPES:
                _fail(path, lineno, f"unknown header key {key!r}; known keys: "
                                    f"{', '.join(sorted(HEADER_TYPES))}")
            try:
                chart[key] = HEADER_TYPES[key](value)
            except ValueError:
                _fail(path, lineno, f"{key} wants a {HEADER_TYPES[key].__name__}, got {value!r}")
            bpm_given = bpm_given or key == "bpm"
            continue

        in_notes = True
        fields = line.split()
        if len(fields) < 2:
            _fail(path, lineno, f"note needs a time and at least one lane, got {line!r}")
        if len(fields) > 3:
            _fail(path, lineno, f"note takes at most 3 columns (time lanes hold), got {len(fields)}")

        when = _parse_time(fields[0], path, lineno, chart["bpm"], bpm_given,
                           chart["beats_per_measure"])
        lanes = _parse_lanes(fields[1], path, lineno)
        hold = _parse_hold(fields[2], path, lineno, chart["bpm"]) if len(fields) == 3 else 0.0
        for lane in lanes:
            hits.append((when, lane, hold))

    if chart["beats_per_measure"] < 1:
        raise DxError(f"{os.path.basename(path)}: beats_per_measure must be at least 1")
    if chart["bpm"] <= 0:
        raise DxError(f"{os.path.basename(path)}: bpm must be positive")

    hits.sort(key=lambda hit: (hit[0], hit[1]))
    lead_in = chart["lead_in"]
    chart["note"] = [lane for _, lane, _ in hits]
    chart["time"] = [int(round(when)) + lead_in for when, _, _ in hits]
    chart["len"] = [int(round(hold)) for _, _, hold in hits]
    if not chart["title"]:
        chart["title"] = os.path.splitext(os.path.basename(path))[0]
    return chart


def load(path):
    """Read a chart off disk. Relative audio paths resolve next to the chart."""
    with open(path, "r", encoding="utf-8") as file:
        chart = loads(file.read(), path)
    chart["path"] = path
    if chart["audio"] and not os.path.isabs(chart["audio"]):
        chart["audio"] = os.path.join(os.path.dirname(os.path.abspath(path)), chart["audio"])
    return chart


def dumps(chart):
    """Render a chart back to .dx text, chords merged and columns lined up."""
    lines = []
    for key in HEADER_TYPES:
        value = chart.get(key)
        if value in (None, "", 0) and DEFAULTS[key] in (None, "", 0):
            continue
        if key == "audio":
            value = os.path.basename(value)
        lines.append(f"{key}: {value}")
    lines.append("")
    lines.append("[notes]")
    lines.append("# when(ms)  lanes  hold")

    lead_in = chart.get("lead_in", 0)
    bpm = chart.get("bpm") or 120.0
    measure_ms = chart.get("beats_per_measure", 4) * 60000.0 / bpm

    # Chords are one line, so gather every lane sharing a time and hold length.
    grouped = {}
    order = []
    for lane, when, hold in zip(chart["note"], chart["time"], chart["len"]):
        key = (when - lead_in, hold)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(lane)

    measure = None
    for when, hold in sorted(order):
        current = int(when // measure_ms) + 1 if measure_ms > 0 else 1
        if current != measure:
            lines.append(f"# measure {current}")
            measure = current
        # set(): a chart holding the same lane twice at one time would otherwise
        # write out as text the reader rejects.
        lanes = ",".join(str(lane) for lane in sorted(set(grouped[(when, hold)])))
        row = f"{when:<10} {lanes:<6}"
        lines.append(f"{row} {hold}".rstrip() if hold else row.rstrip())
    return "\n".join(lines) + "\n"


def dump(chart, path):
    with open(path, "w", encoding="utf-8") as file:
        file.write(dumps(chart))


def peek(path):
    """A chart plus its note count, for the song list.

    This is a full parse rather than a header skim: a chart that only fails when
    the player presses start is worse than one the list quietly leaves out, and
    a second parser to keep in step with `loads` is where that bug would live.
    """
    chart = load(path)
    chart["note_count"] = len(chart["note"])
    return chart


def _main():
    """`python dx.py chart.json ...` converts, `python dx.py chart.dx` checks."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Convert charts to .dx, or check .dx files.")
    parser.add_argument("charts", nargs="+", help="a .json chart to convert, or a .dx to validate")
    args = parser.parse_args()

    for path in args.charts:
        if path.endswith(".dx"):
            try:
                chart = load(path)
            except DxError as error:
                print(f"{path}: {error}")
                continue
            holds = sum(1 for length in chart["len"] if length)
            print(f"{path}: ok -- {len(chart['note'])} notes ({holds} long), {chart['bpm']} BPM")
            continue

        with open(path, "r", encoding="utf-8") as file:
            raw = json.load(file)
        chart = dict(DEFAULTS)
        chart.update({key: raw[key] for key in HEADER_TYPES if key in raw})
        chart["note"] = raw["note"]
        chart["time"] = raw["time"]
        chart["len"] = raw.get("len") or [0] * len(raw["note"])
        if not chart["title"]:
            chart["title"] = os.path.splitext(os.path.basename(path))[0]
        out = os.path.splitext(path)[0] + ".dx"
        dump(chart, out)
        print(f"{path} -> {out} ({len(chart['note'])} notes)")


if __name__ == "__main__":
    _main()
