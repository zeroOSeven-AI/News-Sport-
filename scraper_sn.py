import json
import sys
import re
import requests
import time
from io import BytesIO
from PIL import Image
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import os

# folder za slike
OUTPUT_DIR = "images_sn"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 🔒 STANDARD (IDENTIČNO ZA SVE)
TARGET_WIDTH = 1280
TARGET_HEIGHT = 720

# ============================================
# 🎯 FOCUS LOGIKA
# ============================================
def get_focus_y(ratio):
    if ratio < 1.0:
        return 0.20
    if 1.0 <= ratio <= 1.2:
        return 0.25
    return 0.35

# ============================================
# ✂️ CROP + RESIZE (STRIKTNI STANDARD)
# ============================================
def crop_and_resize(img, focusY):
    # Osiguraj RGB mod
    img = img.convert("RGB")
    w, h = img.size
    target_ratio = 16 / 9
    current_ratio = w / h

    if current_ratio > target_ratio:
        # PREŠIROKA → režemo strane
        new_w = int(h * target_ratio)
        x = (w - new_w) // 2
        cropped = img.crop((x, 0, x + new_w, h))
    else:
        # PREVISOKA → režemo gore/dolje
        new_h = int(w / target_ratio)
        focus_px = int(h * focusY)
        y = max(0, min(h - new_h, focus_px - new_h // 2))
        cropped = img.crop((0, y, w, y + new_h))

    # 🔥 FORCE RESIZE na 1280x720
    return cropped.resize((TARGET_WIDTH, TARGET_HEIGHT), Image.LANCZOS)

# ============================================
# 🖼️ DOWNLOAD + PROCESS
# ============================================
def process_and_get_info(url, index):
    if not url or not url.startswith('http'):
        return "", 0, 0, 0

    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, timeout=15, headers=headers)
        img = Image.open(BytesIO(res.content))

        orig_w, orig_h = img.size
        orig_ratio = round(orig_w / orig_h, 2)

        # Obrada kroz crop i resize
        focusY = get_focus_y(orig_ratio)
        final_img = crop_and_resize(img, focusY)

        filename = f"{OUTPUT_DIR}/sn_{index}.jpg"
        
        # 💾 SAVE: Ključno za micanje margina u Scriptableu
        final_img.save(
            filename, 
            "JPEG", 
            quality=90, 
            subsampling=0,
            dpi=(72, 72),
            icc_profile=None,
            exif=b""
        )

        return filename, TARGET_WIDTH, TARGET_HEIGHT, orig_ratio

    except Exception as e:
        print(f"⚠️ Slika fail na indexu {index}: {e}")
        return "", 0, 0, 0

# ============================================
# 📰 SCRAPER
# ============================================
def scrape_sn():
    url = "https://sportske.jutarnji.hr/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            viewport={'width': 1920, 'height': 1080}
        )
        page =
