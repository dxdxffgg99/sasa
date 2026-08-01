import random
import sys
import time
import json
import os
import cv2
import mediapipe as mp
import pygame

# A small buffer keeps audio latency low, which matters for judging.
pygame.mixer.pre_init(44100, -16, 2, 512)
pygame.init()

INFO = pygame.display.Info()
BORDERLESS = True
FULLSCREEN = False
WIDTH = 768
HEIGHT = INFO.current_h if FULLSCREEN else INFO.current_h-50
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
HOLD_LANE_ALPHA = 80  # the lane stays lit this much while a long note is held

PERFECT_WINDOW = 50
GREAT_WINDOW = 100
GOOD_WINDOW = 160
JUDGE_TEXT_TIME = 400
COMBO_POP_TIME = 130
JUDGE_COLORS = {
    "PERFECT": (255, 226, 120),
    "GREAT": (120, 230, 255),
    "GOOD": (150, 255, 170),
    "MISS": (255, 85, 105),
}

CHART_PATH = sys.argv[1] if len(sys.argv) > 1 else 'game.json'

try:
    with open(CHART_PATH, 'r', encoding='utf-8') as file:
        game_file = file.read()
        game = json.loads(game_file)

except json.JSONDecodeError:
    print("err: JSONDecodeError")
    exit(1)

except Exception as e:
    print(f"{e}")
    exit(1)

# A chart may leave out "len" entirely, in which case every note is a tap.
hold_lengths = game.get("len") or [0] * len(game["note"])

# state: "wait" -> "hold" (long notes being held) -> "done"
notes = [
    {"lane": lane - 1, "time": hit_time, "len": hold_len, "state": "wait"}
    for lane, hit_time, hold_len in zip(game["note"], game["time"], hold_lengths)
]

# Charts from make_chart.py carry their song; hand-written ones may not.
AUDIO = game.get("audio")
LEAD_IN = game.get("lead_in", 0)
SYNC_OFFSET = game.get("offset", 0)  # raise this if the notes arrive later than the song

if AUDIO:
    try:
        pygame.mixer.music.load(AUDIO)
    except pygame.error as e:
        print(f"audio load failed: {e}")
        AUDIO = None

if FULLSCREEN:
    WINDOW_WIDTH, WINDOW_HEIGHT = INFO.current_w, INFO.current_h
else:
    WINDOW_WIDTH, WINDOW_HEIGHT = WIDTH, HEIGHT
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

FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "font.ttf")
combo_font = pygame.font.Font(FONT_PATH, 82)
combo_label_font = pygame.font.Font(FONT_PATH, 20)
judge_font = pygame.font.Font(FONT_PATH, 44)


def make_background():
    """Vertical gradient playfield with alternating lane tints, drawn once."""
    surface = pygame.Surface((WIDTH, HEIGHT))
    for y in range(HEIGHT):
        ratio = y / HEIGHT
        surface.fill(
            tuple(int(top + (bottom - top) * ratio) for top, bottom in zip(BG_TOP_COLOR, BG_BOTTOM_COLOR)),
            (0, y, WIDTH, 1),
        )

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
        surface.fill((*color, int(255 * ratio ** 3)), (0, y, LANE_WIDTH, 1))
    return surface


background = make_background()
lane_flashes = [make_lane_flash(color) for color in LANE_COLORS]
note_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
effect_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

lane_alpha = [0] * LANE_COUNT
spark_time = [-SPARK_TIME] * LANE_COUNT
combo = 0
combo_time = -COMBO_POP_TIME
hit_errors = []
judge_text = ""
judge_time = -JUDGE_TEXT_TIME


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


def rate(error):
    diff = abs(error)
    if diff <= PERFECT_WINDOW:
        return "PERFECT"
    elif diff <= GREAT_WINDOW:
        return "GREAT"
    return "GOOD"


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
    """Let go of a held note. Returns the judgement name, or None if nothing was held."""
    for note in notes:
        if note["state"] != "hold" or note["lane"] != lane:
            continue
        note["state"] = "done"
        # Letting go just before the tail still counts; anything earlier drops it.
        if now >= note["time"] + note["len"] - GOOD_WINDOW:
            return rate(now - note["time"] - note["len"])
        return "MISS"
    return None


running = True
music_started = False
start_ticks = pygame.time.get_ticks()

while running:
    elapsed = pygame.time.get_ticks() - start_ticks

    if AUDIO and not music_started and elapsed >= LEAD_IN:
        pygame.mixer.music.play()
        music_started = True

    # Once the song is playing it owns the clock, so drawing can never drift from it.
    now = elapsed
    if music_started:
        position = pygame.mixer.music.get_pos()
        if position >= 0:
            now = position + LEAD_IN
    now += SYNC_OFFSET

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
            elif event.key in KEY_MAP:
                lane = KEY_MAP[event.key]
                lane_alpha[lane] = ANIMATION_INIT_ALPHA
                result, error = press_lane(lane, now)
                if result is not None:
                    hit_errors.append(error)
                    combo += 1
                    combo_time = now
                    judge_text = result
                    judge_time = now
                    spark_time[lane] = now
        elif event.type == pygame.KEYUP and event.key in KEY_MAP:
            lane = KEY_MAP[event.key]
            result = release_lane(lane, now)
            if result == "MISS":
                combo = 0
                judge_text = "MISS"
                judge_time = now
            elif result is not None:
                combo += 1
                combo_time = now
                judge_text = result
                judge_time = now
                spark_time[lane] = now

    for note in notes:
        if note["state"] == "wait" and now - note["time"] > GOOD_WINDOW:
            note["state"] = "done"
            combo = 0
            judge_text = "MISS"
            judge_time = now
        elif note["state"] == "hold":
            # Held all the way to the tail: complete it without needing a release.
            if now >= note["time"] + note["len"]:
                note["state"] = "done"
                combo += 1
                combo_time = now
                judge_text = "PERFECT"
                judge_time = now
                spark_time[note["lane"]] = now
            else:
                # Keep the lane lit for as long as the key is down.
                lane_alpha[note["lane"]] = max(lane_alpha[note["lane"]], HOLD_LANE_ALPHA)

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
        color = LANE_COLORS[note["lane"]]
        head_y = note_y(note["time"], now)

        if note["len"] > 0:
            tail_y = note_y(note["time"] + note["len"], now)
            if tail_y < 0:
                continue
            # While held, the body is consumed by the judge line instead of falling past it.
            if note["state"] == "hold":
                head_y = min(head_y, JUDGE_LINE_HEIGHT)
            alpha = HOLD_HELD_ALPHA if note["state"] == "hold" else HOLD_BODY_ALPHA
            pygame.draw.rect(note_surface, (*color, alpha), pygame.Rect(
                note["lane"] * LANE_WIDTH + (LANE_WIDTH - HOLD_WIDTH) // 2,
                tail_y,
                HOLD_WIDTH,
                max(0, head_y - tail_y),
            ), border_radius=4)
            draw_note_head(note["lane"], tail_y, color)
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

    if combo > 0:
        combo_image = combo_font.render(str(combo), True, (255, 255, 255))
        pop = max(0.0, 1 - (now - combo_time) / COMBO_POP_TIME)
        scale = 1 + 0.22 * pop
        combo_image = pygame.transform.smoothscale(
            combo_image, (int(combo_image.get_width() * scale), int(combo_image.get_height() * scale))
        )
        center = (WIDTH // 2, JUDGE_LINE_HEIGHT - 290)
        screen.blit(combo_image, combo_image.get_rect(center=center))
        label_image = combo_label_font.render("COMBO", True, (150, 160, 200))
        screen.blit(label_image, label_image.get_rect(center=(center[0], center[1] + 58)))

    elapsed = now - judge_time
    if elapsed < JUDGE_TEXT_TIME:
        ratio = elapsed / JUDGE_TEXT_TIME
        judge_image = judge_font.render(judge_text, True, JUDGE_COLORS[judge_text])
        judge_image.set_alpha(255 - int(255 * ratio ** 2))
        screen.blit(judge_image, judge_image.get_rect(center=(WIDTH // 2, JUDGE_LINE_HEIGHT - 180 - int(18 * ratio))))

    if PLAY_X or PLAY_Y:
        window.fill((0, 0, 0))
    window.blit(screen, (PLAY_X, PLAY_Y))
    pygame.display.flip()
    clock.tick(60)
pygame.quit()

# Your average timing error is the part of the offset that hardware latency causes.
if len(hit_errors) >= 10:
    hit_errors.sort()
    median = hit_errors[len(hit_errors) // 2]
    average = sum(hit_errors) / len(hit_errors)
    print(f"hits: {len(hit_errors)}  median error: {median:+d} ms  average: {average:+.1f} ms")
    print(f"suggested offset: {SYNC_OFFSET - median} (currently {SYNC_OFFSET})")
    print("positive error means you pressed late, so the notes were arriving early")
else:
    print("play at least 10 notes to get an offset suggestion")
