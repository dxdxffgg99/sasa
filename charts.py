"""Reading chart files (.dx and legacy .json) and listing them for the menu."""
import json
import os

import dx


def load_json_chart(path):
    """Read a legacy .json chart into the same shape dx.load returns."""
    with open(path, "r", encoding="utf-8") as file:
        raw = json.load(file)
    chart = dict(dx.DEFAULTS)
    chart.update({key: raw[key] for key in dx.HEADER_TYPES if key in raw})
    chart["note"] = raw["note"]
    chart["time"] = raw["time"]
    chart["len"] = raw.get("len") or [0] * len(raw["note"])
    chart["path"] = path
    if not chart["title"]:
        chart["title"] = os.path.splitext(os.path.basename(path))[0]
    if chart["audio"] and not os.path.isabs(chart["audio"]):
        chart["audio"] = os.path.join(os.path.dirname(os.path.abspath(path)), chart["audio"])
    return chart


def load_chart(path):
    return load_json_chart(path) if path.endswith(".json") else dx.load(path)


def find_charts(directory):
    """Every readable chart in `directory`; anything that fails to parse is named
    on stdout and left out of the list rather than breaking the menu."""
    found = []
    for name in sorted(os.listdir(directory)):
        path = os.path.join(directory, name)
        try:
            if name.endswith(".dx"):
                found.append(dx.peek(path))
            elif name.endswith(".json"):
                chart = load_json_chart(path)
                chart["note_count"] = len(chart["note"])
                found.append(chart)
        except (dx.DxError, json.JSONDecodeError, KeyError, OSError) as error:
            print(f"skipping {name}: {error}")
    return sorted(found, key=lambda chart: chart["title"].lower())
