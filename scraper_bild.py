import json
import sys
import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_title(title):
    if not title:
        return ""
    # Mičemo višestruke razmake
    title = re.sub(r'\s+', ' ', title)
    # Mičemo uobičajeno smeće na početku
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
                    # --- KLJUČNA IZMJENA ZA ČISTI NASLOV ---
                    # Prvo kopiramo element da ne uništimo originalni soup
                    import copy
                    title_copy = copy.copy(title_elem)
                    
                    # Brišemo sve spanove (tamo Bild drži nadnaslove/kickere)
                    for span in title_copy.find_all('span'):
                        span.decompose()
                    
                    # Sad uzimamo tekst - ostaje samo čisti, glavni naslov
                    raw_title = title_copy.get_text(strip=True)
                    
                    # Ako je nakon čišćenja ostalo nešto prekratko, preskoči
                    if len(raw_title) < 10:
                        continue
                    
                    title = clean_title(raw_title)
                    
                    link = link_elem['href']
                    if link.startswith('/'):
                        link = "https://sportbild.bild.de" + link
                    
                    # --- SLIKE ---
                    image = ""
                    if img_elem:
                        image = (img_elem.get('data-src') or 
                                 img_elem.get('src') or "")
                        
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
            
            print(f"Gotovo! Spremljeno {len(news_items)} čistih vijesti.")
            browser.close()

        except Exception as e:
            print(f"Greška: {e}")
            if 'browser' in locals():
                browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_bild()
