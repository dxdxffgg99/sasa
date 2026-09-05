import json
import sys

import pygame

import config as c
import dx
from charts import find_charts, load_chart
from gameplay import play
from menu import results_screen, song_select


def main():
    # A chart named on the command line skips the menu and plays straight away.
    if len(sys.argv) > 1:
        try:
            chart = load_chart(sys.argv[1])
        except (dx.DxError, json.JSONDecodeError, OSError, KeyError) as error:
            print(f"{error}")
            return 1
        status, results = play(chart)
        if status == "finished":
            results_screen(chart, results)
        return 0

    charts = find_charts(c.SONG_DIR)
    if not charts:
        print(f"no .dx charts in {c.SONG_DIR}; make one with make_chart.py")
        return 1

    index = 0
    while True:
        index, picked = song_select(charts, index)
        if picked is None:
            return 0
        try:
            # Re-read rather than reuse the listed copy, so editing a .dx and
            # picking it again plays the edit without restarting the game.
            chart = load_chart(picked["path"])
        except (dx.DxError, json.JSONDecodeError, OSError, KeyError) as error:
            print(f"{picked['path']}: {error}")
            continue
        status, results = play(chart)
        if status == "quit":
            return 0
        if status == "finished" and not results_screen(chart, results):
            return 0


if __name__ == "__main__":
    code = main()
    pygame.quit()
    sys.exit(code)
