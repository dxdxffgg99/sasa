import random
import sys
import time
import json
import math
import os
import cv2
import mediapipe as mp
import pygame

import dx

pygame.mixer.pre_init(44100, -16, 2, 512)
pygame.init()

INFO = pygame.display.Info()
BORDERLESS = True
FULLSCREEN = False
WIDTH = 768
HEIGHT = INFO.current_h if FULLSCREEN else INFO.current_h-50
SIDE_PANEL_WIDTH = 260
GAME_CAPTION = "sasa rhythm"
LANE_COUNT = 4
LANE_WIDTH = WIDTH // LANE_COUNT
JUDGE_LINE_HEIGHT = HEIGHT-192
KEY_MAP = {pygame.K_z: 0, pygame.K_x: 1, pygame.K_PERIOD: 2, pygame.K_SLASH: 3}

BG_TOP_COLOR = (8, 8, 18)
BG_BOTTOM_COLOR = (28, 20, 48)
LANE_TINT = (255, 255, 255, 8)
SEPERATE_LINE_COLOR = (70, 70, 95)
JUDGE_LINE_COLOR = (255, 255, 255)
JUDGE_GLOW_COLOR = (120, 190, 255)
LANE_COLORS = [
    (235, 240, 255),
    (95, 170, 255),
    (95, 170, 255),
    (235, 240, 255),
]

ANIMATION_FADE_SPEED = 14
ANIMATION_INIT_ALPHA = 150
SPARK_TIME = 260
SPARK_RADIUS = 90

NOTE_HEIGHT = 26
NOTE_MARGIN = 8
NOTE_RADIUS = 7
NOTE_FALL_TIME = 1200

HOLD_WIDTH = LANE_WIDTH - NOTE_MARGIN * 2 - 10
HOLD_BODY_ALPHA = 150
HOLD_HELD_ALPHA = 230
HOLD_MISSED_ALPHA = 70
HOLD_LANE_ALPHA = 80
MISSED_NOTE_COLOR = (110, 110, 120)

SYNC = 0
SCORE_P = 1
SIGMA_EARLY = 60.0
SIGMA_LATE = 40.0
GOOD_WINDOW = 40
THRESHOLD_MARVELOUS = 0.99
THRESHOLD_PERFECT = 0.85
THRESHOLD_GREAT = 0.75
THRESHOLD_GOOD = 0.5

JUDGE_TEXT_TIME = 400
COMBO_POP_TIME = 130
JUDGE_NAMES = ["MARVELOUS", "PERFECT", "GREAT", "GOOD", "MISS"]
JUDGE_COLORS = {
    "MARVELOUS": (255, 255, 255),
    "PERFECT": (202, 87, 255),
    "GREAT": (97, 165, 255),
    "GOOD": (255, 190, 79),
    "MISS": (255, 79, 85),
}
JUDGE_HISTORY_LENGTH = 8
PANEL_BG_COLOR = (14, 14, 26, 160)
PANEL_LABEL_COLOR = (150, 160, 200)

SONG_DIR = os.path.dirname(os.path.abspath(__file__))
SELECT_ROW_HEIGHT = 86
SELECT_SCROLL_SPEED = 0.22  # fraction of the remaining distance eaten per frame
ACCENT_COLOR = (120, 190, 255)
DIM_TEXT_COLOR = (140, 150, 185)
END_HANG_TIME = 1500  # ms of empty playfield before the results come up

if FULLSCREEN:
    WINDOW_WIDTH, WINDOW_HEIGHT = INFO.current_w, INFO.current_h
else:
    WINDOW_WIDTH, WINDOW_HEIGHT = WIDTH + SIDE_PANEL_WIDTH * 2, HEIGHT
    os.environ["SDL_VIDEO_CENTERED"] = "1"

window = pygame.display.set_mode(
    (WINDOW_WIDTH, WINDOW_HEIGHT),
    pygame.NOFRAME if BORDERLESS or FULLSCREEN else 0,
)
# The playfield is drawn on its own surface, then centered inside the window.
screen = pygame.Surface((WIDTH, HEIGHT))
PLAY_X = (WINDOW_WIDTH - WIDTH) // 2
PLAY_Y = (WINDOW_HEIGHT - HEIGHT) // 2

pygame.display.set_caption(GAME_CAPTION)
clock = pygame.time.Clock()

FONT_PATH = os.path.join(SONG_DIR, "font.ttf")
judge_font = pygame.font.Font(FONT_PATH, 44)
panel_label_font = pygame.font.Font(FONT_PATH, 18)
panel_score_font = pygame.font.Font(FONT_PATH, 40)
panel_combo_font = pygame.font.Font(FONT_PATH, 60)
panel_history_font = pygame.font.Font(FONT_PATH, 24)
heading_font = pygame.font.Font(FONT_PATH, 56)
song_title_font = pygame.font.Font(FONT_PATH, 34)
song_sub_font = pygame.font.Font(FONT_PATH, 19)
meta_font = pygame.font.Font(FONT_PATH, 22)
footer_font = pygame.font.Font(FONT_PATH, 20)


def make_gradient(size, top_color, bottom_color):
    width, height = size
    surface = pygame.Surface(size)
    for y in range(height):
        ratio = y / height
        surface.fill(
            tuple(int(top + (bottom - top) * ratio) for top, bottom in zip(top_color, bottom_color)),
            (0, y, width, 1),
        )
    return surface


def make_background():
    """Vertical gradient playfield with alternating lane tints, drawn once."""
    surface = make_gradient((WIDTH, HEIGHT), BG_TOP_COLOR, BG_BOTTOM_COLOR)

    tint = pygame.Surface((LANE_WIDTH, HEIGHT), pygame.SRCALPHA)
    tint.fill(LANE_TINT)
    for i in (1, 2):
        surface.blit(tint, (i * LANE_WIDTH, 0))

    for i in range(1, LANE_COUNT):
        pygame.draw.line(surface, SEPERATE_LINE_COLOR, (LANE_WIDTH * i, 0), (LANE_WIDTH * i, HEIGHT), width=2)
    return surface


def make_lane_flash(color):
    """Key press glow: transparent at the top, solid at the judge line."""
    surface = pygame.Surface((LANE_WIDTH, JUDGE_LINE_HEIGHT), pygame.SRCALPHA)
    for y in range(JUDGE_LINE_HEIGHT):
        ratio = y / JUDGE_LINE_HEIGHT
        surface.fill((*color, int(255 * ratio ** 4)), (0, y, LANE_WIDTH, 1))
    return surface


background = make_background()
menu_background = make_gradient((WINDOW_WIDTH, WINDOW_HEIGHT), BG_TOP_COLOR, BG_BOTTOM_COLOR)
lane_flashes = [make_lane_flash(color) for color in LANE_COLORS]
note_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
effect_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)


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


def draw_footer(surface, text):
    image = footer_font.render(text, True, DIM_TEXT_COLOR)
    surface.blit(image, image.get_rect(midbottom=(WINDOW_WIDTH // 2, WINDOW_HEIGHT - 34)))


def draw_song_row(surface, chart, rect, selected):
    """One entry of the song list: title, artist, and the chart's numbers."""
    if selected:
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill((*ACCENT_COLOR, 26))
        surface.blit(panel, rect.topleft)
        pygame.draw.rect(surface, (*ACCENT_COLOR, 255), pygame.Rect(rect.left, rect.top, 5, rect.height))

    text_x = rect.left + 34
    title_color = (255, 255, 255) if selected else (190, 198, 225)
    title_image = song_title_font.render(chart["title"], True, title_color)
    surface.blit(title_image, (text_x, rect.top + 14))

    subtitle = chart["artist"] or "unknown artist"
    subtitle_image = song_sub_font.render(subtitle, True, DIM_TEXT_COLOR)
    surface.blit(subtitle_image, (text_x, rect.top + 52))

    facts = f"{chart['note_count']} notes   BPM {chart['bpm']:g}"
    facts_image = meta_font.render(facts, True, DIM_TEXT_COLOR)
    surface.blit(facts_image, facts_image.get_rect(midright=(rect.right - 36, rect.centery + 12)))

    label = chart["difficulty"] or os.path.splitext(os.path.basename(chart["path"]))[1].lstrip(".").upper()
    if chart["level"]:
        label = f"{label}  {chart['level']}"
    label_image = meta_font.render(label, True, ACCENT_COLOR if selected else DIM_TEXT_COLOR)
    surface.blit(label_image, label_image.get_rect(midright=(rect.right - 36, rect.centery - 18)))


def song_select(charts, index=0):
    """Pick a chart. Returns (index, chart) or (index, None) when quitting."""
    scroll = float(index)
    list_left = max(40, (WINDOW_WIDTH - 900) // 2)
    list_width = min(900, WINDOW_WIDTH - 80)
    list_top = 190
    visible_rows = max(1, (WINDOW_HEIGHT - list_top - 110) // SELECT_ROW_HEIGHT)
    clip = pygame.Rect(list_left, list_top, list_width, visible_rows * SELECT_ROW_HEIGHT)

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return index, None
            if event.type != pygame.KEYDOWN:
                continue
            if event.key == pygame.K_ESCAPE:
                return index, None
            elif event.key in (pygame.K_UP, pygame.K_LEFT):
                index = (index - 1) % len(charts)
            elif event.key in (pygame.K_DOWN, pygame.K_RIGHT):
                index = (index + 1) % len(charts)
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                return index, charts[index]

        # Keep the highlighted row parked in the middle of the list, easing there
        # so a held arrow key reads as a scroll rather than a series of jumps.
        target = min(max(index - visible_rows // 2, 0), max(0, len(charts) - visible_rows))
        scroll += (target - scroll) * SELECT_SCROLL_SPEED
        if abs(target - scroll) < 0.01:
            scroll = float(target)

        window.blit(menu_background, (0, 0))

        heading = heading_font.render("sasa", True, (255, 255, 255))
        window.blit(heading, (list_left, 74))
        count = meta_font.render(f"{len(charts)}곡", True, DIM_TEXT_COLOR)
        window.blit(count, count.get_rect(bottomright=(list_left + list_width, 74 + heading.get_height() - 6)))
        pygame.draw.line(window, SEPERATE_LINE_COLOR, (list_left, list_top - 22),
                         (list_left + list_width, list_top - 22), width=2)

        window.set_clip(clip)
        for i, chart in enumerate(charts):
            top = list_top + int((i - scroll) * SELECT_ROW_HEIGHT)
            if top + SELECT_ROW_HEIGHT < list_top or top > clip.bottom:
                continue
            draw_song_row(window, chart, pygame.Rect(list_left, top, list_width, SELECT_ROW_HEIGHT - 8), i == index)
        window.set_clip(None)

        draw_footer(window, "↑ ↓  선택      ENTER  시작      ESC  종료")
        pygame.display.flip()
        clock.tick(60)


def results_screen(chart, results):
    """Score breakdown, plus the offset the hits suggest. Returns False to quit."""
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    return True

        window.blit(menu_background, (0, 0))
        center_x = WINDOW_WIDTH // 2

        title_image = heading_font.render(chart["title"], True, (255, 255, 255))
        window.blit(title_image, title_image.get_rect(midtop=(center_x, 70)))
        cleared = "CLEAR" if results["counts"]["MISS"] == 0 else "COMPLETE"
        state_image = meta_font.render(cleared, True, ACCENT_COLOR)
        window.blit(state_image, state_image.get_rect(midtop=(center_x, 140)))

        score_image = panel_combo_font.render(f"{results['score']:,}", True, (255, 255, 255))
        window.blit(score_image, score_image.get_rect(midtop=(center_x, 190)))
        accuracy_image = meta_font.render(
            f"정확도 {results['accuracy']:.2f}%    최대 콤보 {results['max_combo']}", True, DIM_TEXT_COLOR)
        window.blit(accuracy_image, accuracy_image.get_rect(midtop=(center_x, 262)))

        top = 320
        for i, name in enumerate(JUDGE_NAMES):
            row_y = top + i * 44
            name_image = panel_history_font.render(name, True, JUDGE_COLORS[name])
            window.blit(name_image, name_image.get_rect(midright=(center_x - 30, row_y)))
            count_image = panel_history_font.render(str(results["counts"][name]), True, (235, 240, 255))
            window.blit(count_image, count_image.get_rect(midleft=(center_x + 30, row_y)))

        advice_y = top + len(JUDGE_NAMES) * 44 + 40
        for line in results["advice"]:
            advice_image = song_sub_font.render(line, True, DIM_TEXT_COLOR)
            window.blit(advice_image, advice_image.get_rect(midtop=(center_x, advice_y)))
            advice_y += 30

        draw_footer(window, "ENTER  곡 선택으로      ESC  종료")
        pygame.display.flip()
        clock.tick(60)


def note_y(note_time, now):
    """Screen height a note of that timestamp sits at right now."""
    return JUDGE_LINE_HEIGHT * (1 - (note_time - now) / NOTE_FALL_TIME)


def draw_note_head(lane, y, color):
    body = pygame.Rect(
        lane * LANE_WIDTH + NOTE_MARGIN,
        y - NOTE_HEIGHT // 2,
        LANE_WIDTH - NOTE_MARGIN * 2,
        NOTE_HEIGHT,
    )
    pygame.draw.rect(note_surface, (*color, 70), body.inflate(10, 10), border_radius=NOTE_RADIUS + 3)
    pygame.draw.rect(note_surface, color, body, border_radius=NOTE_RADIUS)
    pygame.draw.rect(note_surface, (255, 255, 255), body.inflate(0, -NOTE_HEIGHT + 6), border_radius=3)


def judge_score(error):
    """Score(dt): a Gaussian centered on Sync, asymmetric between early/late hits."""
    diff = error - SYNC
    sigma = SIGMA_EARLY if diff < 0 else SIGMA_LATE
    return math.exp(-SCORE_P * diff ** 2 / (2 * sigma ** 2))


def rate(error):
    s = judge_score(error)
    if s >= THRESHOLD_MARVELOUS:
        return "MARVELOUS"
    elif s >= THRESHOLD_PERFECT:
        return "PERFECT"
    elif s >= THRESHOLD_GREAT:
        return "GREAT"
    elif s >= THRESHOLD_GOOD:
        return "GOOD"
    return "MISS"


def offset_advice(hit_errors, sync_offset):
    """What the player's own timing says the chart's offset should have been."""
    if len(hit_errors) < 10:
        return ["10노트 이상 쳐야 오프셋을 추천할 수 있어요"]
    ordered = sorted(hit_errors)
    median = ordered[len(ordered) // 2]
    average = sum(ordered) / len(ordered)
    print(f"hits: {len(ordered)}  median error: {median:+d} ms  average: {average:+.1f} ms")
    print(f"suggested offset: {sync_offset - median} (currently {sync_offset})")
    print("positive error means you pressed late, so the notes were arriving early")
    return [
        f"판정 오차 중앙값 {median:+d} ms (평균 {average:+.1f} ms)",
        f"추천 offset: {sync_offset - median}  (현재 {sync_offset})",
    ]


def play(chart):
    """Run one chart. Returns (status, results) with status quit/abort/finished."""
    # state: "wait" -> "hold" (long notes being held) -> "done"
    notes = [
        {"lane": lane - 1, "time": hit_time, "len": hold_len, "state": "wait"}
        for lane, hit_time, hold_len in zip(chart["note"], chart["time"], chart["len"])
    ]
    audio = chart["audio"]
    lead_in = chart["lead_in"]
    sync_offset = chart["offset"]  # raise this if the notes arrive later than the song

    if audio:
        try:
            pygame.mixer.music.load(audio)
        except pygame.error as error:
            print(f"audio load failed: {error}")
            audio = None

    lane_alpha = [0] * LANE_COUNT
    spark_time = [-SPARK_TIME] * LANE_COUNT
    combo = 0
    max_combo = 0
    combo_time = -COMBO_POP_TIME
    hit_errors = []
    judge_text = ""
    judge_time = -JUDGE_TEXT_TIME
    score = 0
    judge_history = []
    counts = {name: 0 for name in JUDGE_NAMES}
    accuracy_sum = 0.0
    judged = 0

    def record_judge(name, now, error=0):
        """Track score and the left-panel judgement history for any judged hit."""
        nonlocal score, accuracy_sum, judged
        # A miss lands just outside the window, where the Gaussian is still worth
        # most of a point, so it has to be zeroed rather than scored.
        value = 0.0 if name == "MISS" else judge_score(error)
        score += round(value * 1000)
        accuracy_sum += value
        judged += 1
        counts[name] += 1
        judge_history.append((name, now))
        if len(judge_history) > JUDGE_HISTORY_LENGTH:
            judge_history.pop(0)

    def press_lane(lane, now):
        """Hit the closest waiting note in `lane`. Returns the judgement name or None."""
        target = None
        for note in notes:
            if note["state"] != "wait" or note["lane"] != lane:
                continue
            if abs(note["time"] - now) > GOOD_WINDOW:
                continue
            if target is None or abs(note["time"] - now) < abs(target["time"] - now):
                target = note

        if target is None:
            return None, 0

        error = now - target["time"]  # positive means the key was pressed late
        # A long note stays alive until its tail is reached or the key is let go.
        target["state"] = "hold" if target["len"] > 0 else "done"
        return rate(error), error

    def release_lane(lane, now):
        """Let go of a held note. Returns the judgement name and error, or (None, 0) if nothing was held."""
        for note in notes:
            if note["state"] != "hold" or note["lane"] != lane:
                continue
            # Letting go just before the tail still counts; anything earlier drops it,
            # but the body keeps falling through instead of vanishing on the spot.
            if now >= note["time"] + note["len"] - GOOD_WINDOW:
                note["state"] = "done"
                error = now - note["time"] - note["len"]
                return rate(error), error
            note["state"] = "missed"
            return "MISS", 0
        return None, 0

    status = "finished"
    music_started = False
    cleared_at = None
    start_ticks = pygame.time.get_ticks()

    while True:
        elapsed = pygame.time.get_ticks() - start_ticks

        if audio and not music_started and elapsed >= lead_in:
            pygame.mixer.music.play()
            music_started = True

        # Once the song is playing it owns the clock, so drawing can never drift from it.
        now = elapsed
        if music_started:
            position = pygame.mixer.music.get_pos()
            if position >= 0:
                now = position + lead_in
        now += sync_offset

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                status = "quit"
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    status = "abort"
                elif event.key in KEY_MAP:
                    lane = KEY_MAP[event.key]
                    lane_alpha[lane] = ANIMATION_INIT_ALPHA
                    result, error = press_lane(lane, now)
                    if result == "MISS":
                        hit_errors.append(error)
                        combo = 0
                        judge_text = "MISS"
                        judge_time = now
                        record_judge(result, now, error)
                    elif result is not None:
                        hit_errors.append(error)
                        combo += 1
                        max_combo = max(max_combo, combo)
                        combo_time = now
                        judge_text = result
                        judge_time = now
                        spark_time[lane] = now
                        record_judge(result, now, error)
            elif event.type == pygame.KEYUP and event.key in KEY_MAP:
                lane = KEY_MAP[event.key]
                result, error = release_lane(lane, now)
                if result == "MISS":
                    combo = 0
                    judge_text = "MISS"
                    judge_time = now
                    record_judge(result, now, error)
                elif result is not None:
                    combo += 1
                    max_combo = max(max_combo, combo)
                    combo_time = now
                    judge_text = result
                    judge_time = now
                    spark_time[lane] = now
                    record_judge(result, now, error)

        if status != "finished":
            break

        for note in notes:
            if note["state"] == "wait" and now - note["time"] > GOOD_WINDOW:
                # A missed long note keeps falling through instead of disappearing; taps just vanish.
                note["state"] = "missed" if note["len"] > 0 else "done"
                combo = 0
                judge_text = "MISS"
                judge_time = now
                record_judge("MISS", now, now - note["time"])
            elif note["state"] == "missed":
                if note_y(note["time"] + note["len"], now) > HEIGHT:
                    note["state"] = "done"
            elif note["state"] == "hold":
                # Held all the way to the tail: complete it without needing a release.
                if now >= note["time"] + note["len"]:
                    note["state"] = "done"
                    combo += 1
                    max_combo = max(max_combo, combo)
                    combo_time = now
                    judge_text = "MARVELOUS"
                    judge_time = now
                    spark_time[note["lane"]] = now
                    record_judge("MARVELOUS", now)
                else:
                    # Keep the lane lit for as long as the key is down.
                    lane_alpha[note["lane"]] = max(lane_alpha[note["lane"]], HOLD_LANE_ALPHA)

        # The chart is over once the last note is gone; let the field empty out first.
        if cleared_at is None and all(note["state"] == "done" for note in notes):
            cleared_at = now
        if cleared_at is not None and now - cleared_at >= END_HANG_TIME:
            break

        screen.blit(background, (0, 0))

        for i, flash in enumerate(lane_flashes):
            if lane_alpha[i] > 0:
                flash.set_alpha(lane_alpha[i])
                screen.blit(flash, (i * LANE_WIDTH, 0))
            lane_alpha[i] = max(0, lane_alpha[i] - ANIMATION_FADE_SPEED)

        note_surface.fill((0, 0, 0, 0))
        for note in notes:
            if note["state"] == "done":
                continue
            color = MISSED_NOTE_COLOR if note["state"] == "missed" else LANE_COLORS[note["lane"]]
            head_y = note_y(note["time"], now)

            if note["len"] > 0:
                tail_y = note_y(note["time"] + note["len"], now)
                if head_y < 0:
                    continue
                # While held, the body is consumed by the judge line instead of falling past it.
                # A missed hold keeps falling straight through the line instead of being clipped.
                if note["state"] == "hold":
                    head_y = min(head_y, JUDGE_LINE_HEIGHT)
                visible_tail_y = max(0, tail_y)
                if note["state"] == "hold":
                    alpha = HOLD_HELD_ALPHA
                elif note["state"] == "missed":
                    alpha = HOLD_MISSED_ALPHA
                else:
                    alpha = HOLD_BODY_ALPHA
                pygame.draw.rect(note_surface, (*color, alpha), pygame.Rect(
                    note["lane"] * LANE_WIDTH + (LANE_WIDTH - HOLD_WIDTH) // 2,
                    visible_tail_y,
                    HOLD_WIDTH,
                    max(0, head_y - visible_tail_y),
                ), border_radius=4)
                draw_note_head(note["lane"], visible_tail_y, color)
            elif head_y < 0:
                continue

            draw_note_head(note["lane"], head_y, color)
        screen.blit(note_surface, (0, 0))

        effect_surface.fill((0, 0, 0, 0))
        for i in range(LANE_COUNT):
            spark_elapsed = now - spark_time[i]
            if spark_elapsed >= SPARK_TIME:
                continue
            ratio = spark_elapsed / SPARK_TIME
            pygame.draw.circle(
                effect_surface,
                (*LANE_COLORS[i], int(180 * (1 - ratio))),
                (i * LANE_WIDTH + LANE_WIDTH // 2, JUDGE_LINE_HEIGHT),
                int(SPARK_RADIUS * ratio),
                width=max(1, int(10 * (1 - ratio))),
            )
        screen.blit(effect_surface, (0, 0))

        for offset, alpha in ((10, 40), (6, 70), (3, 120)):
            glow = pygame.Surface((WIDTH, offset * 2), pygame.SRCALPHA)
            glow.fill((*JUDGE_GLOW_COLOR, alpha))
            screen.blit(glow, (0, JUDGE_LINE_HEIGHT - offset))
        pygame.draw.line(screen, JUDGE_LINE_COLOR, (0, JUDGE_LINE_HEIGHT), (WIDTH, JUDGE_LINE_HEIGHT), width=3)

        since_judge = now - judge_time
        if since_judge < JUDGE_TEXT_TIME:
            ratio = since_judge / JUDGE_TEXT_TIME
            judge_image = judge_font.render(judge_text, True, JUDGE_COLORS[judge_text])
            judge_image.set_alpha(255 - int(255 * ratio ** 2))
            screen.blit(judge_image, judge_image.get_rect(center=(WIDTH // 2, JUDGE_LINE_HEIGHT - 180 - int(18 * ratio))))

        if PLAY_X or PLAY_Y:
            window.fill((0, 0, 0))
        window.blit(screen, (PLAY_X, PLAY_Y))

        # Left panel: judgement info (current + recent history).
        if PLAY_X > 0:
            left_panel = pygame.Surface((PLAY_X, HEIGHT), pygame.SRCALPHA)
            left_panel.fill(PANEL_BG_COLOR)
            label_image = panel_label_font.render("판정", True, PANEL_LABEL_COLOR)
            left_panel.blit(label_image, label_image.get_rect(midtop=(PLAY_X // 2, 40)))

            if judge_history:
                current_name, current_time = judge_history[-1]
                current_ratio = min(1.0, (now - current_time) / JUDGE_TEXT_TIME)
                current_image = judge_font.render(current_name, True, JUDGE_COLORS[current_name])
                current_image.set_alpha(255 - int(180 * current_ratio ** 2))
                left_panel.blit(current_image, current_image.get_rect(center=(PLAY_X // 2, 100)))

            history_top = 170
            for i, (name, hit_time) in enumerate(reversed(judge_history[:-1])):
                row_image = panel_history_font.render(name, True, JUDGE_COLORS[name])
                row_image.set_alpha(max(60, 220 - i * 24))
                left_panel.blit(row_image, row_image.get_rect(midtop=(PLAY_X // 2, history_top + i * 34)))

            window.blit(left_panel, (0, PLAY_Y))

        # Right panel: song, combo and score.
        right_panel_x = PLAY_X + WIDTH
        right_panel_width = WINDOW_WIDTH - right_panel_x
        if right_panel_width > 0:
            right_panel = pygame.Surface((right_panel_width, HEIGHT), pygame.SRCALPHA)
            right_panel.fill(PANEL_BG_COLOR)
            center_x = right_panel_width // 2

            song_image = panel_label_font.render(chart["title"], True, PANEL_LABEL_COLOR)
            right_panel.blit(song_image, song_image.get_rect(midtop=(center_x, 14)))

            combo_label_image = panel_label_font.render("COMBO", True, PANEL_LABEL_COLOR)
            right_panel.blit(combo_label_image, combo_label_image.get_rect(midtop=(center_x, 40)))

            combo_image = panel_combo_font.render(str(combo), True, (255, 255, 255))
            pop = max(0.0, 1 - (now - combo_time) / COMBO_POP_TIME)
            scale = 1 + 0.22 * pop
            combo_image = pygame.transform.smoothscale(
                combo_image, (int(combo_image.get_width() * scale), int(combo_image.get_height() * scale))
            )
            right_panel.blit(combo_image, combo_image.get_rect(center=(center_x, 100)))

            score_label_image = panel_label_font.render("SCORE", True, PANEL_LABEL_COLOR)
            right_panel.blit(score_label_image, score_label_image.get_rect(midtop=(center_x, 220)))
            score_image = panel_score_font.render(f"{score:,}", True, (255, 255, 255))
            right_panel.blit(score_image, score_image.get_rect(midtop=(center_x, 250)))

            window.blit(right_panel, (right_panel_x, PLAY_Y))

        pygame.display.flip()
        clock.tick(60)

    pygame.mixer.music.stop()
    results = {
        "score": score,
        "counts": counts,
        "max_combo": max_combo,
        "accuracy": 100 * accuracy_sum / judged if judged else 0.0,
        "advice": offset_advice(hit_errors, sync_offset),
    }
    return status, results


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

    charts = find_charts(SONG_DIR)
    if not charts:
        print(f"no .dx charts in {SONG_DIR}; make one with make_chart.py")
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
