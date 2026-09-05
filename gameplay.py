"""The play loop: note motion, hit judging, and the in-game HUD."""
import pygame

import assets
import audio
import config as c
from judging import judge_score, offset_advice, rate


def open_mixer_for(path, declared_rate=0):
    """Re-open the mixer at the song's own sample rate.

    Whatever the mixer is opened at, SDL resamples everything else to it, and
    that resampler loses length: a 48 kHz song through a 44.1 kHz mixer runs
    0.129% short, so the song ends 190 ms before the chart thinks it does. The
    chart records the rate it was built against; failing that we read the file.
    """
    wanted = declared_rate or audio.native_rate(path) or c.DEFAULT_MIXER_RATE
    current = pygame.mixer.get_init()
    if current and current[0] == wanted:
        return
    try:
        pygame.mixer.quit()
        pygame.mixer.init(wanted, -16, 2, 512)
    except pygame.error as error:
        print(f"could not open the mixer at {wanted} Hz ({error}); notes may drift")
        pygame.mixer.init()
    got = pygame.mixer.get_init()
    if got and got[0] != wanted:
        print(f"mixer opened at {got[0]} Hz, not {wanted} Hz; notes may drift")


def note_y(note_time, now):
    """Screen height a note of that timestamp sits at right now."""
    return c.JUDGE_LINE_HEIGHT * (1 - (note_time - now) / c.NOTE_FALL_TIME)


def draw_note_head(lane, y, color):
    body = pygame.Rect(
        lane * c.LANE_WIDTH + c.NOTE_MARGIN,
        y - c.NOTE_HEIGHT // 2,
        c.LANE_WIDTH - c.NOTE_MARGIN * 2,
        c.NOTE_HEIGHT,
    )
    pygame.draw.rect(assets.note_surface, (*color, 70), body.inflate(10, 10), border_radius=c.NOTE_RADIUS + 3)
    pygame.draw.rect(assets.note_surface, color, body, border_radius=c.NOTE_RADIUS)
    pygame.draw.rect(assets.note_surface, (255, 255, 255), body.inflate(0, -c.NOTE_HEIGHT + 6), border_radius=3)


def play(chart):
    """Run one chart. Returns (status, results) with status quit/abort/finished."""
    # state: "wait" -> "hold" (long notes being held) -> "done"
    notes = [
        {"lane": lane - 1, "time": hit_time, "len": hold_len, "state": "wait"}
        for lane, hit_time, hold_len in zip(chart["note"], chart["time"], chart["len"])
    ]
    song = chart["audio"]
    lead_in = chart["lead_in"]
    sync_offset = chart["offset"]  # raise this if the notes arrive later than the song

    if song:
        open_mixer_for(song, chart["sample_rate"])
        try:
            pygame.mixer.music.load(song)
        except pygame.error as error:
            print(f"audio load failed: {error}")
            song = None

    lane_alpha = [0] * c.LANE_COUNT
    spark_time = [-c.SPARK_TIME] * c.LANE_COUNT
    combo = 0
    max_combo = 0
    combo_time = -c.COMBO_POP_TIME
    hit_errors = []
    judge_text = ""
    judge_time = -c.JUDGE_TEXT_TIME
    score = 0
    judge_history = []
    counts = {name: 0 for name in c.JUDGE_NAMES}
    accuracy_sum = 0.0
    judged = 0

    def record_judge(name, now, error=0):
        """Track score and the left-panel judgement history for any judged hit."""
        nonlocal score, accuracy_sum, judged
        # A miss lands just outside the window, where the Gaussian is still worth
        # most of a point, so it has to be zeroed rather than scored.
        value = 0.0 if name == "MISS" else judge_score(error)
        score = max(0, score - c.MISS_PENALTY) if name == "MISS" else score + round(value * 1000)
        accuracy_sum += value
        judged += 1
        counts[name] += 1
        judge_history.append((name, now))
        if len(judge_history) > c.JUDGE_HISTORY_LENGTH:
            judge_history.pop(0)

    def press_lane(lane, now):
        """Hit the closest waiting note in `lane`. Returns the judgement name or None."""
        target = None
        for note in notes:
            if note["state"] != "wait" or note["lane"] != lane:
                continue
            if abs(note["time"] - now) > c.GOOD_WINDOW:
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
            if now >= note["time"] + note["len"] - c.GOOD_WINDOW:
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

        if song and not music_started and elapsed >= lead_in:
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
                elif event.key in c.KEY_MAP:
                    lane = c.KEY_MAP[event.key]
                    lane_alpha[lane] = c.ANIMATION_INIT_ALPHA
                    result, error = press_lane(lane, now)
                    if result == "MISS":
                        hit_errors.append((now, error))
                        combo = 0
                        judge_text = "MISS"
                        judge_time = now
                        record_judge(result, now, error)
                    elif result is not None:
                        hit_errors.append((now, error))
                        combo += 1
                        max_combo = max(max_combo, combo)
                        combo_time = now
                        judge_text = result
                        judge_time = now
                        spark_time[lane] = now
                        record_judge(result, now, error)
            elif event.type == pygame.KEYUP and event.key in c.KEY_MAP:
                lane = c.KEY_MAP[event.key]
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
            if note["state"] == "wait" and now - note["time"] > c.GOOD_WINDOW:
                # A missed long note keeps falling through instead of disappearing; taps just vanish.
                note["state"] = "missed" if note["len"] > 0 else "done"
                combo = 0
                judge_text = "MISS"
                judge_time = now
                record_judge("MISS", now, now - note["time"])
            elif note["state"] == "missed":
                if note_y(note["time"] + note["len"], now) > c.HEIGHT:
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
                    lane_alpha[note["lane"]] = max(lane_alpha[note["lane"]], c.HOLD_LANE_ALPHA)

        # The chart is over once the last note is gone; let the field empty out first.
        if cleared_at is None and all(note["state"] == "done" for note in notes):
            cleared_at = now
        if cleared_at is not None and now - cleared_at >= c.END_HANG_TIME:
            break

        c.screen.blit(assets.background, (0, 0))

        for i, flash in enumerate(assets.lane_flashes):
            if lane_alpha[i] > 0:
                flash.set_alpha(lane_alpha[i])
                c.screen.blit(flash, (i * c.LANE_WIDTH, 0))
            lane_alpha[i] = max(0, lane_alpha[i] - c.ANIMATION_FADE_SPEED)

        assets.note_surface.fill((0, 0, 0, 0))
        for note in notes:
            if note["state"] == "done":
                continue
            color = c.MISSED_NOTE_COLOR if note["state"] == "missed" else c.LANE_COLORS[note["lane"]]
            head_y = note_y(note["time"], now)

            if note["len"] > 0:
                tail_y = note_y(note["time"] + note["len"], now)
                if head_y < 0:
                    continue
                # While held, the body is consumed by the judge line instead of falling past it.
                # A missed hold keeps falling straight through the line instead of being clipped.
                if note["state"] == "hold":
                    head_y = min(head_y, c.JUDGE_LINE_HEIGHT)
                visible_tail_y = max(0, tail_y)
                if note["state"] == "hold":
                    alpha = c.HOLD_HELD_ALPHA
                elif note["state"] == "missed":
                    alpha = c.HOLD_MISSED_ALPHA
                else:
                    alpha = c.HOLD_BODY_ALPHA
                pygame.draw.rect(assets.note_surface, (*color, alpha), pygame.Rect(
                    note["lane"] * c.LANE_WIDTH + (c.LANE_WIDTH - c.HOLD_WIDTH) // 2,
                    visible_tail_y,
                    c.HOLD_WIDTH,
                    max(0, head_y - visible_tail_y),
                ), border_radius=4)
                draw_note_head(note["lane"], visible_tail_y, color)
            elif head_y < 0:
                continue

            draw_note_head(note["lane"], head_y, color)
        c.screen.blit(assets.note_surface, (0, 0))

        assets.effect_surface.fill((0, 0, 0, 0))
        for i in range(c.LANE_COUNT):
            spark_elapsed = now - spark_time[i]
            if spark_elapsed >= c.SPARK_TIME:
                continue
            ratio = spark_elapsed / c.SPARK_TIME
            pygame.draw.circle(
                assets.effect_surface,
                (*c.LANE_COLORS[i], int(180 * (1 - ratio))),
                (i * c.LANE_WIDTH + c.LANE_WIDTH // 2, c.JUDGE_LINE_HEIGHT),
                int(c.SPARK_RADIUS * ratio),
                width=max(1, int(10 * (1 - ratio))),
            )
        c.screen.blit(assets.effect_surface, (0, 0))

        for offset, alpha in ((10, 40), (6, 70), (3, 120)):
            glow = pygame.Surface((c.WIDTH, offset * 2), pygame.SRCALPHA)
            glow.fill((*c.JUDGE_GLOW_COLOR, alpha))
            c.screen.blit(glow, (0, c.JUDGE_LINE_HEIGHT - offset))
        pygame.draw.line(c.screen, c.JUDGE_LINE_COLOR, (0, c.JUDGE_LINE_HEIGHT), (c.WIDTH, c.JUDGE_LINE_HEIGHT), width=3)

        since_judge = now - judge_time
        if since_judge < c.JUDGE_TEXT_TIME:
            ratio = since_judge / c.JUDGE_TEXT_TIME
            judge_image = c.judge_font.render(judge_text, True, c.JUDGE_COLORS[judge_text])
            judge_image.set_alpha(255 - int(255 * ratio ** 2))
            c.screen.blit(judge_image, judge_image.get_rect(center=(c.WIDTH // 2, c.JUDGE_LINE_HEIGHT - 180 - int(18 * ratio))))

        if c.PLAY_X or c.PLAY_Y:
            c.window.fill((0, 0, 0))
        c.window.blit(c.screen, (c.PLAY_X, c.PLAY_Y))

        # Left panel: judgement info (current + recent history).
        if c.PLAY_X > 0:
            left_panel = pygame.Surface((c.PLAY_X, c.HEIGHT), pygame.SRCALPHA)
            left_panel.fill(c.PANEL_BG_COLOR)
            label_image = c.panel_label_font.render("판정", True, c.PANEL_LABEL_COLOR)
            left_panel.blit(label_image, label_image.get_rect(midtop=(c.PLAY_X // 2, 40)))

            if judge_history:
                current_name, current_time = judge_history[-1]
                current_ratio = min(1.0, (now - current_time) / c.JUDGE_TEXT_TIME)
                current_image = c.judge_font.render(current_name, True, c.JUDGE_COLORS[current_name])
                current_image.set_alpha(255 - int(180 * current_ratio ** 2))
                left_panel.blit(current_image, current_image.get_rect(center=(c.PLAY_X // 2, 100)))

            history_top = 170
            for i, (name, hit_time) in enumerate(reversed(judge_history[:-1])):
                row_image = c.panel_history_font.render(name, True, c.JUDGE_COLORS[name])
                row_image.set_alpha(max(60, 220 - i * 24))
                left_panel.blit(row_image, row_image.get_rect(midtop=(c.PLAY_X // 2, history_top + i * 34)))

            c.window.blit(left_panel, (0, c.PLAY_Y))

        # Right panel: song, combo and score.
        right_panel_x = c.PLAY_X + c.WIDTH
        right_panel_width = c.WINDOW_WIDTH - right_panel_x
        if right_panel_width > 0:
            right_panel = pygame.Surface((right_panel_width, c.HEIGHT), pygame.SRCALPHA)
            right_panel.fill(c.PANEL_BG_COLOR)
            center_x = right_panel_width // 2

            song_image = c.panel_label_font.render(chart["title"], True, c.PANEL_LABEL_COLOR)
            right_panel.blit(song_image, song_image.get_rect(midtop=(center_x, 14)))

            combo_label_image = c.panel_label_font.render("COMBO", True, c.PANEL_LABEL_COLOR)
            right_panel.blit(combo_label_image, combo_label_image.get_rect(midtop=(center_x, 40)))

            combo_image = c.panel_combo_font.render(str(combo), True, (255, 255, 255))
            pop = max(0.0, 1 - (now - combo_time) / c.COMBO_POP_TIME)
            scale = 1 + 0.22 * pop
            combo_image = pygame.transform.smoothscale(
                combo_image, (int(combo_image.get_width() * scale), int(combo_image.get_height() * scale))
            )
            right_panel.blit(combo_image, combo_image.get_rect(center=(center_x, 100)))

            score_label_image = c.panel_label_font.render("SCORE", True, c.PANEL_LABEL_COLOR)
            right_panel.blit(score_label_image, score_label_image.get_rect(midtop=(center_x, 220)))
            score_image = c.panel_score_font.render(f"{score:,}", True, (255, 255, 255))
            right_panel.blit(score_image, score_image.get_rect(midtop=(center_x, 250)))

            c.window.blit(right_panel, (right_panel_x, c.PLAY_Y))

        pygame.display.flip()
        c.clock.tick(60)

    pygame.mixer.music.stop()
    results = {
        "score": score,
        "counts": counts,
        "max_combo": max_combo,
        "accuracy": 100 * accuracy_sum / judged if judged else 0.0,
        "advice": offset_advice(hit_errors, sync_offset,
                                max(chart["time"]) - lead_in if chart["time"] else 0),
    }
    return status, results
