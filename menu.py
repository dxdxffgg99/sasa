"""Song select and results screens, plus the drifting note background behind them."""
import os
import random

import pygame

import assets
import config as c


def menu_note_alpha(x, width):
    """Dim in the middle, bright at the edges.

    The song list lives in the middle of the screen, so the drift stays out at
    the sides where it reads as motion instead of as clutter behind the text.
    """
    away = min(1.0, abs(x + width / 2 - c.WINDOW_WIDTH / 2) / (c.WINDOW_WIDTH / 2))
    low, high = c.SELECT_BG_ALPHA
    return int(low + (high - low) * away ** 1.5)


def menu_note_column():
    """A lane to fall down, so the drift reads as notes rather than as debris."""
    span = c.WINDOW_WIDTH / c.SELECT_BG_COLUMNS
    width = int(span * 0.5)
    x = random.randrange(c.SELECT_BG_COLUMNS) * span + (span - width) / 2
    return x, width


def make_menu_notes():
    """Faint notes drifting down behind the song list, so the menu is not still."""
    notes = []
    for _ in range(c.SELECT_BG_NOTES):
        x, width = menu_note_column()
        notes.append({
            "x": x,
            # Spread them above and across the screen so the very first frame
            # already looks like a stream rather than a row dropping in.
            "y": random.uniform(-c.WINDOW_HEIGHT, c.WINDOW_HEIGHT),
            "speed": random.uniform(*c.SELECT_BG_SPEED),
            "alpha": menu_note_alpha(x, width),
            "width": width,
            "color": random.choice(c.LANE_COLORS),
        })
    return notes


def draw_menu_notes(surface, notes, dt):
    assets.menu_effect_surface.fill((0, 0, 0, 0))
    for note in notes:
        note["y"] += note["speed"] * dt
        if note["y"] > c.WINDOW_HEIGHT:
            note["y"] = -c.SELECT_BG_HEIGHT
            note["x"], note["width"] = menu_note_column()
            note["alpha"] = menu_note_alpha(note["x"], note["width"])
            note["color"] = random.choice(c.LANE_COLORS)
        pygame.draw.rect(
            assets.menu_effect_surface, (*note["color"], note["alpha"]),
            pygame.Rect(int(note["x"]), int(note["y"]), note["width"], c.SELECT_BG_HEIGHT),
            border_radius=3,
        )
    surface.blit(assets.menu_effect_surface, (0, 0))


def beat_pulse(elapsed, bpm):
    """1.0 on the beat, falling to 0 by the next one, at the song's own tempo.

    The menu breathing at the highlighted chart's bpm says how fast the song is
    before the player commits to it -- the number alone does not land the same way.
    """
    beat_ms = 60000 / (bpm or 120)
    return (1 - (elapsed % beat_ms) / beat_ms) ** c.BEAT_DECAY


def draw_footer(surface, text):
    image = c.footer_font.render(text, True, c.DIM_TEXT_COLOR)
    surface.blit(image, image.get_rect(midbottom=(c.WINDOW_WIDTH // 2, c.WINDOW_HEIGHT - 34)))


def draw_song_row(surface, chart, rect, selected, pulse=0.0):
    """One entry of the song list: title, artist, and the chart's numbers."""
    if selected:
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill((*c.ACCENT_COLOR, 26 + int(20 * pulse)))
        surface.blit(panel, rect.topleft)
        bar = 5 + int(4 * pulse)
        pygame.draw.rect(surface, c.ACCENT_COLOR, pygame.Rect(rect.left, rect.top, bar, rect.height))

    text_x = rect.left + 34
    title_color = (255, 255, 255) if selected else (190, 198, 225)
    title_image = c.song_title_font.render(chart["title"], True, title_color)
    surface.blit(title_image, (text_x, rect.top + 14))

    subtitle = chart["artist"] or "unknown artist"
    subtitle_image = c.song_sub_font.render(subtitle, True, c.DIM_TEXT_COLOR)
    surface.blit(subtitle_image, (text_x, rect.top + 52))

    facts = f"{chart['note_count']} notes   BPM {chart['bpm']:g}"
    facts_image = c.meta_font.render(facts, True, c.DIM_TEXT_COLOR)
    surface.blit(facts_image, facts_image.get_rect(midright=(rect.right - 36, rect.centery + 12)))

    label = chart["difficulty"] or os.path.splitext(os.path.basename(chart["path"]))[1].lstrip(".").upper()
    if chart["level"]:
        label = f"{label}  {chart['level']}"
    label_image = c.meta_font.render(label, True, c.ACCENT_COLOR if selected else c.DIM_TEXT_COLOR)
    surface.blit(label_image, label_image.get_rect(midright=(rect.right - 36, rect.centery - 18)))


def song_select(charts, index=0):
    """Pick a chart. Returns (index, chart) or (index, None) when quitting."""
    scroll = float(index)
    notes = make_menu_notes()
    # Anchored at the moment the highlight moved, so each song's pulse starts
    # on its own downbeat instead of inheriting the previous song's phase.
    beat_anchor = pygame.time.get_ticks()
    list_left = max(40, (c.WINDOW_WIDTH - 900) // 2)
    list_width = min(900, c.WINDOW_WIDTH - 80)
    list_top = 190
    visible_rows = max(1, (c.WINDOW_HEIGHT - list_top - 110) // c.SELECT_ROW_HEIGHT)
    clip = pygame.Rect(list_left, list_top, list_width, visible_rows * c.SELECT_ROW_HEIGHT)

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
                beat_anchor = pygame.time.get_ticks()
            elif event.key in (pygame.K_DOWN, pygame.K_RIGHT):
                index = (index + 1) % len(charts)
                beat_anchor = pygame.time.get_ticks()
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                return index, charts[index]

        # Keep the highlighted row parked in the middle of the list, easing there
        # so a held arrow key reads as a scroll rather than a series of jumps.
        target = min(max(index - visible_rows // 2, 0), max(0, len(charts) - visible_rows))
        scroll += (target - scroll) * c.SELECT_SCROLL_SPEED
        if abs(target - scroll) < 0.01:
            scroll = float(target)

        pulse = beat_pulse(pygame.time.get_ticks() - beat_anchor, charts[index]["bpm"])

        c.window.blit(assets.menu_background, (0, 0))
        draw_menu_notes(c.window, notes, c.clock.get_time() / 1000)

        heading = c.heading_font.render("sasa", True, (255, 255, 255))
        c.window.blit(heading, (list_left, 74))
        count = c.meta_font.render(f"{len(charts)}곡", True, c.DIM_TEXT_COLOR)
        c.window.blit(count, count.get_rect(bottomright=(list_left + list_width, 74 + heading.get_height() - 6)))
        rule_y = list_top - 22
        pygame.draw.line(c.window, c.SEPERATE_LINE_COLOR, (list_left, rule_y),
                         (list_left + list_width, rule_y), width=2)
        # The rule lights up on the beat, so the whole header keeps the tempo.
        glow = pygame.Surface((list_width, 2), pygame.SRCALPHA)
        glow.fill((*c.ACCENT_COLOR, int(150 * pulse)))
        c.window.blit(glow, (list_left, rule_y - 1))

        c.window.set_clip(clip)
        for i, chart in enumerate(charts):
            top = list_top + int((i - scroll) * c.SELECT_ROW_HEIGHT)
            if top + c.SELECT_ROW_HEIGHT < list_top or top > clip.bottom:
                continue
            draw_song_row(c.window, chart, pygame.Rect(list_left, top, list_width, c.SELECT_ROW_HEIGHT - 8),
                          i == index, pulse)
        c.window.set_clip(None)

        draw_footer(c.window, "↑ ↓  선택      ENTER  시작      ESC  종료")
        pygame.display.flip()
        c.clock.tick(60)


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

        c.window.blit(assets.menu_background, (0, 0))
        center_x = c.WINDOW_WIDTH // 2

        title_image = c.heading_font.render(chart["title"], True, (255, 255, 255))
        c.window.blit(title_image, title_image.get_rect(midtop=(center_x, 70)))
        cleared = "CLEAR" if results["counts"]["MISS"] == 0 else "COMPLETE"
        state_image = c.meta_font.render(cleared, True, c.ACCENT_COLOR)
        c.window.blit(state_image, state_image.get_rect(midtop=(center_x, 140)))

        score_image = c.panel_combo_font.render(f"{results['score']:,}", True, (255, 255, 255))
        c.window.blit(score_image, score_image.get_rect(midtop=(center_x, 190)))
        accuracy_image = c.meta_font.render(
            f"정확도 {results['accuracy']:.2f}%    최대 콤보 {results['max_combo']}", True, c.DIM_TEXT_COLOR)
        c.window.blit(accuracy_image, accuracy_image.get_rect(midtop=(center_x, 262)))

        top = 320
        for i, name in enumerate(c.JUDGE_NAMES):
            row_y = top + i * 44
            name_image = c.panel_history_font.render(name, True, c.JUDGE_COLORS[name])
            c.window.blit(name_image, name_image.get_rect(midright=(center_x - 30, row_y)))
            count_image = c.panel_history_font.render(str(results["counts"][name]), True, (235, 240, 255))
            c.window.blit(count_image, count_image.get_rect(midleft=(center_x + 30, row_y)))

        advice_y = top + len(c.JUDGE_NAMES) * 44 + 40
        for line in results["advice"]:
            advice_image = c.song_sub_font.render(line, True, c.DIM_TEXT_COLOR)
            c.window.blit(advice_image, advice_image.get_rect(midtop=(center_x, advice_y)))
            advice_y += 30

        draw_footer(c.window, "ENTER  곡 선택으로      ESC  종료")
        pygame.display.flip()
        c.clock.tick(60)
