"""Display setup, fonts, and every tunable constant used across the game."""
import os
import sys

import pygame

pygame.mixer.pre_init(44100, -16, 2, 512)
pygame.init()

INFO = pygame.display.Info()
BORDERLESS = sys.platform.startswith("linux")
FULLSCREEN = False
SCREEN_MARGIN = 50 if BORDERLESS else 100
WIDTH = 768
HEIGHT = INFO.current_h if FULLSCREEN else INFO.current_h - SCREEN_MARGIN
SIDE_PANEL_WIDTH = 260
GAME_CAPTION = "sasa rhythm"
LANE_COUNT = 4
LANE_WIDTH = WIDTH // LANE_COUNT
JUDGE_LINE_HEIGHT = HEIGHT - 192
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
JUDGE_SCALE = 1.25
SIGMA_EARLY = 60.0 * JUDGE_SCALE
SIGMA_LATE = 40.0 * JUDGE_SCALE
GOOD_WINDOW = int(40 * JUDGE_SCALE)
THRESHOLD_MARVELOUS = 0.99
THRESHOLD_PERFECT = 0.85
THRESHOLD_GREAT = 0.75
THRESHOLD_GOOD = 0.5
MISS_PENALTY = 500

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
SELECT_BG_NOTES = 44
SELECT_BG_SPEED = (30, 95)   # px per second
SELECT_BG_ALPHA = (7, 44)    # at the middle of the screen, and out at the edges
SELECT_BG_COLUMNS = 15
SELECT_BG_HEIGHT = 7
BEAT_DECAY = 3.0  # how sharply the on-beat flash falls away before the next one
DIM_TEXT_COLOR = (140, 150, 185)
END_HANG_TIME = 1500  # ms of empty playfield before the results come up
DEFAULT_MIXER_RATE = 44100
DRIFT_WARN = 0.0002  # fractional drift worth telling the player about (0.02%)
MIN_HITS_FOR_DRIFT = 20

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
