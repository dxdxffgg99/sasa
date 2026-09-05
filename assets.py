"""Surfaces built once at startup: gradients, lane flashes, and draw targets."""
import pygame

import config as c


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
    surface = make_gradient((c.WIDTH, c.HEIGHT), c.BG_TOP_COLOR, c.BG_BOTTOM_COLOR)

    tint = pygame.Surface((c.LANE_WIDTH, c.HEIGHT), pygame.SRCALPHA)
    tint.fill(c.LANE_TINT)
    for i in (1, 2):
        surface.blit(tint, (i * c.LANE_WIDTH, 0))

    for i in range(1, c.LANE_COUNT):
        pygame.draw.line(surface, c.SEPERATE_LINE_COLOR, (c.LANE_WIDTH * i, 0), (c.LANE_WIDTH * i, c.HEIGHT), width=2)
    return surface


def make_lane_flash(color):
    """Key press glow: transparent at the top, solid at the judge line."""
    surface = pygame.Surface((c.LANE_WIDTH, c.JUDGE_LINE_HEIGHT), pygame.SRCALPHA)
    for y in range(c.JUDGE_LINE_HEIGHT):
        ratio = y / c.JUDGE_LINE_HEIGHT
        surface.fill((*color, int(255 * ratio ** 4)), (0, y, c.LANE_WIDTH, 1))
    return surface


background = make_background()
menu_background = make_gradient((c.WINDOW_WIDTH, c.WINDOW_HEIGHT), c.BG_TOP_COLOR, c.BG_BOTTOM_COLOR)
lane_flashes = [make_lane_flash(color) for color in c.LANE_COLORS]
note_surface = pygame.Surface((c.WIDTH, c.HEIGHT), pygame.SRCALPHA)
effect_surface = pygame.Surface((c.WIDTH, c.HEIGHT), pygame.SRCALPHA)
menu_effect_surface = pygame.Surface((c.WINDOW_WIDTH, c.WINDOW_HEIGHT), pygame.SRCALPHA)
