import random
import time
import json
import os
import cv2
import mediapipe as mp
import pygame

pygame.init()

INFO = pygame.display.Info()
HEIGHT = INFO.current_h - 50
WIDTH = 768
BG_COLOR = (0,0,0)
GAME_CAPTION = "sasa rhythm"
SEPERATE_LINE_COLOR = (128,128,128)

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

screen = pygame.display.set_mode((WIDTH, HEIGHT-50))
pygame.display.set_caption(GAME_CAPTION)
clock = pygame.time.Clock()

running = True

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False

    screen.fill(BG_COLOR)
    
    for i in range(1,4):
        pygame.draw.line(screen, SEPERATE_LINE_COLOR, (192*i, 0), (192*i, HEIGHT), width=4)
    
    pygame.display.flip()
    clock.tick(60)
pygame.quit()