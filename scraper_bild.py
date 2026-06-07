import json
import logging
import re
from typing import Any, Dict, List, Optional  # <-- Ovdje je sada dodan Optional
import httpx

# ==============================================================================
# KONFIGURACIJA
# ==============================================================================
API_URL = "https://sportbild.bild.de/api/v1/editorial/sportbild/sections/home/teaser-list"
MAX_NEWS_ITEMS = 20

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def get_focus_y(w: int, h: int) -> float:
    ratio = round(w / h, 2)
    if ratio >= 1.6: return 0.30
    if 0.9 <= ratio <= 1.1: return 0.22
    if 1.2 <= ratio <= 1.6: return 0.35
    return 0.5

def clean_title(title: str) -> str:
    if not title:
        return ""
    return re.sub(r'^[:\s–|-]+', '', title).strip()

def extract_best_image(teaser: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Izvlači glavnu sliku iz API strukture artikla."""
    images = teaser.get("images", [])
    if not images and "image" in teaser:
        images = [teaser["image"]]
        
    for img_obj in images:
        url = img_obj.get("url") or img_obj.get("src")
        if not url:
            continue
            
        if "placeholder" in url.lower() or "sys-fallback" in url.lower():
            continue
            
        w = int(img_obj.get("width", 0) or img_obj.get("w", 992))
        h = int(img_obj.get("height", 0) or img_obj.get("h", 558))
        
        if "{width}" in url:
            url = url.replace("{width}", "992")
            w = 992
            
        return {
            "url": url,
            "w": w,
            "h": h,
            "focus_y": get_focus_y(w, h)
        }
    return None

def main():
    logging.info("🚀 Pokrećem ultra-brzo API skeniranje (FlashScore stil)...")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15'
    }
    
    try:
        with httpx.Client(timeout=10.0, headers=headers) as client:
            response = client.get(API_URL)
            if response.status_code != 200:
                logging.error(f"❌ API server vratio status: {response.status_code}")
                return
                
            data = response.json()
            
        items = data.get("items", []) or data.get("teasers", []) or data.get("data", [])
        logging.info(f"📊 API je isporučio {len(items)} sirovih stavki.")
        
        news_items: List[Dict[str, Any]] = []
        
        for item in items:
            if len(news_items) >= MAX_NEWS_ITEMS:
                break
                
            title = clean_title(item.get("title") or item.get("headline"))
            link = item.get("shareUrl") or item.get("url")
            
            if not title or not link:
                continue
                
            image_info = extract_best_image(item)
            if not image_info:
                continue
                
            news_items.append({
                "title": title,
                "link": link,
                "image_url": image_info["url"],
                "w": image_info["w"],
                "h": image_info["h"],
                "focus_y": image_info["focus_y"],
                "source_title1": "SPORT",
                "source_title2": "BILD",
                "source_color": "#fc4e4e",
                "flag": "🇩🇪"
            })
            
        if news_items:
            with open("bild.json", "w", encoding="utf-8") as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            logging.info(f"🎉 Gotovo! 'bild.json' kreiran s {len(news_items)} čistih vijesti.")
        else:
            logging.warning("⚠️ Skripta je završila, ali niti jedan artikl nije imao važeću sliku.")
            
    except Exception as e:
        logging.error(f"❌ Kritična greška pri radu s API-jem: {e}")

if __name__ == "__main__":
    main()
