import random
import time
import json
import os
import cv2
import mediapipe as mp
import pygame

pygame.init()

INFO = pygame.display.Info()
WIDTH = 768
HEIGHT = INFO.current_h-50
BG_COLOR = (0,0,0)
GAME_CAPTION = "sasa rhythm"
SEPERATE_LINE_COLOR = (128,128,128)
JUDGE_LINE_HEIGHT = HEIGHT-384
LANE_COUNT = 4
LANE_WIDTH = WIDTH // LANE_COUNT
ANIMATION_FADE_SPEED = 15
ANIMATION_INIT_ALPHA = 128
KEY_MAP = {pygame.K_z: 0, pygame.K_x: 1, pygame.K_PERIOD: 2, pygame.K_SLASH: 3}

try:
    with open('game.json', 'r', encoding='utf-8') as file:
        game_file = file.read();
        game = json.loads(game_file)

except json.JSONDecodeError:
    print(f"err: JSONDecodeError")
    exit(0)
    
except Exception as e:
    print(f"{e}")
    exit(0)

screen = pygame.display.set_mode((WIDTH, HEIGHT))
animate_surfaces = [
    pygame.Surface((LANE_WIDTH, HEIGHT), pygame.SRCALPHA),
    pygame.Surface((LANE_WIDTH, HEIGHT), pygame.SRCALPHA),
    pygame.Surface((LANE_WIDTH, HEIGHT), pygame.SRCALPHA),
    pygame.Surface((LANE_WIDTH, HEIGHT), pygame.SRCALPHA),
]
note_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

pygame.display.set_caption(GAME_CAPTION)
clock = pygame.time.Clock()

lane_alpha = [0,0, 0, 0]


running = True

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
            elif event.key in KEY_MAP:
                lane_alpha[KEY_MAP[event.key]] = ANIMATION_INIT_ALPHA

    screen.fill(BG_COLOR)
    
    for i in range(1,4):
        pygame.draw.line(screen, SEPERATE_LINE_COLOR, (LANE_WIDTH * i, 0), (LANE_WIDTH * i, HEIGHT), width=4)
    pygame.draw.line(screen, SEPERATE_LINE_COLOR, (0, JUDGE_LINE_HEIGHT), (768, JUDGE_LINE_HEIGHT), width=4)

    for i, surf in enumerate(animate_surfaces):
        surf.fill((0, 0, 0, 0))
        pygame.draw.rect(surf, (255, 255, 255, lane_alpha[i]), surf.get_rect())
        screen.blit(surf, (i * LANE_WIDTH, 0))
        lane_alpha[i] = max(0, lane_alpha[i] - ANIMATION_FADE_SPEED)
    
    pygame.display.flip()
    clock.tick(60)
pygame.quit()