import random
import time
import json
import os

import cv2
import mediapipe as mp
import pygame

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