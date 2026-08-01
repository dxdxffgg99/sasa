import random
import time
import json
import os

import cv2
import mediapipe as mp
import pygame

pygame.init()

HEIGHT = pygame.display.Info().current_h
WIDTH = 768
BG_COLOR = (0,0,0)
GAME_CAPTION = "sasa rhythm"

try:
    with open('games.json', 'r', encoding='utf-8') as file:
        content = file.read()
        json.loads(content)

except json.JSONDecodeError:
    print(f"err: JSONDecodeError")
    exit(0)
    
except Exception as e:
    print(f"{e}")
    exit(0)

screen = pygame.display.set_mode((WIDTH, HEIGHT-50))
pygame.display.set_caption(GAME_CAPTION)

running = True

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    screen.fill(BG_COLOR) 

    pygame.display.flip()

pygame.quit()