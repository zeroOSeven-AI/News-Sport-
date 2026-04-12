import json
import sys
import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_title(title):
    if not title:
        return ""
    
    # 1. Bild često spoji Kicker i Headline (npr. "BaumannJeder hat seinen Senf...")
    # Tražimo granicu gdje malo slovo dodiruje veliko
    # Ali umjesto da odrežemo sve prije, samo umetnemo razmak da rečenica ostane čitava
    title = re.sub(r'([a-zčćžšđ])([A-ZČĆŽŠĐ])', r'\1 \2', title)

    # 2. Ako i dalje želiš izbaciti taj prvi dio (Kicker), koristimo ovaj trik:
    # Ako naslov počne s jednom riječi pa odmah ide veliko slovo (npr. "Freiburg Gelingt..."),
    # mičemo tu prvu riječ.
    parts = title.split(' ', 1)
    if len(parts) > 1 and parts[0].strip().isalpha():
        # Provjeravamo je li druga riječ počela velikim slovom (znak novog naslova)
        if parts[1][0].isupper():
            title = parts[1]

    # 3. Standardno čišćenje separatora
    title = re.sub(r'^[:\s–|-]+', '', title)
    return title.strip()

def scrape_bild():
    url = "https://m.sportbild.bild.de/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
        )
        page = context.new_page()

        try:
            print(f"Otvaram: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            page.evaluate("window.scrollBy(0, 2000)")
            page.wait_for_timeout(3000) 
            
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            news_items = []
            articles = soup.find_all('article')

            for art in articles:
                title_elem = art.find(['h2', 'h3', 'h4'], class_=re.compile(r'headline|title', re.I))
                if not title_elem:
                    title_elem = art.find(['h2', 'h3', 'h4'])
                
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if title_elem and link_elem:
                    # Uzimamo tekst sa razmakom da se Kicker i Headline ne slijepe
                    raw_title = title_elem.get_text(" ", strip=True) 
                    
                    if len(raw_title) < 10:
                        continue
                    
                    title = clean_title(raw_title)
                    
                    link = link_elem['href']
                    if link.startswith('/'):
                        link = "https://sportbild.bild.de" + link
                    
                    # --- SLIKE ---
                    image = ""
                    if img_elem:
                        image = (img_elem.get('data-src') or img_elem.get('src') or "")
                        
                    if not image or "1x1" in image:
                        source_tag = art.find('source')
                        if source_tag:
                            image = source_tag.get('srcset', '').split(' ')[0]

                    if image and image.startswith('/'):
                        image = "https://sportbild.bild.de" + image

                    if not any(item['title'] == title for item in news_items):
                        news_items.append({
                            "title": title,
                            "link": link,
                            "image": image,
                            "source_title1": "SPORT",
                            "source_title2": "BILD",
                            "source_color": "#e20613",
                            "flag": "🇩🇪"
                        })

                if len(news_items) >= 20:
                    break

            with open('bild.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            
            print(f"Uspješno spremljeno {len(news_items)} vijesti u bild.json")
            browser.close()

        except Exception as e:
            print(f"Greška: {e}")
            if 'browser' in locals():
                browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_bild()
