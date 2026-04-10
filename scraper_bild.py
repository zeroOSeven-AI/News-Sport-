import json
import sys
import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_title(title):
    if not title: return ""
    title = re.sub(r'^(BILDplus|KOMENTAR|VIDEO|FOTOS|LIVE|EXKLUSIV)\s*', '', title, flags=re.IGNORECASE)
    return title.strip()

def scrape_bild():
    # Vraćamo se na glavnu sportsku stranicu koja je stabilnija za scraping
    url = "https://www.bild.de/sport/fussball/fotos-videos-news-66166138.bild.html"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 2000}
        )
        page = context.new_page()

        try:
            print(f"Napad na Bild... Scraper pali dvije cigare ovaj put.")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Duža pauza da JS odradi svoje
            page.wait_for_timeout(10000) 
            
            # Skrolanje da se aktiviraju slike
            for _ in range(4):
                page.evaluate("window.scrollBy(0, 800)")
                page.wait_for_timeout(1000)
            
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            news_items = []
            
            # Bild sada koristi puno 'article' tagova ali i 'div' s posebnim data-atributima
            articles = soup.find_all(['article', 'div'], class_=re.compile(r'teaser|m-entry|hentry', re.I))

            if not articles:
                # Ako ne nađe ništa, idemo na "brute force" - traži sve linkove koji imaju naslov u sebi
                articles = soup.select('a[href*=".bild.html"]')

            for art in articles:
                # Tražimo bilo koji tekstualni element koji liči na naslov
                title_elem = art.find(['h2', 'h3', 'span', 'p'], class_=re.compile(r'headline|title|text|label', re.I))
                if not title_elem and art.name == 'a':
                    title_elem = art
                
                link_elem = art if art.name == 'a' else art.find('a', href=True)
                img_elem = art.find('img')

                if title_elem and link_elem:
                    raw_title = title_elem.get_text(" ", strip=True)
                    title = clean_title(raw_title)
                    
                    if len(title) < 15: continue
                        
                    link = link_elem['href']
                    if link.startswith('/'):
                        link = "https://www.bild.de" + link
                    
                    # --- BILD SLIKA FIX ---
                    image = ""
                    if img_elem:
                        image = (img_elem.get('src') or 
                                 img_elem.get('data-src') or 
                                 img_elem.get('srcset', '').split(' ')[0])
                    
                    # Ako nema slike u articleu, tražimo najbližu sliku (Bild nekad odvaja img od teksta)
                    if not image or "1x1" in image:
                        # Pokušaj naći sliku unutar istog roditelja
                        parent = art.find_parent('div')
                        if parent:
                            nearby_img = parent.find('img')
                            if nearby_img:
                                image = nearby_img.get('src') or nearby_img.get('data-src') or ""

                    if image and image.startswith('//'): image = "https:" + image
                    elif image and image.startswith('/'): image = "https://www.bild.de" + image

                    if not any(item['title'] == title for item in news_items):
                        news_items.append({
                            "title": title,
                            "link": link,
                            "image": image,
                            "source_title1": "BILD",
                            "source_title2": "SPORT",
                            "source_color": "#fc4e4e",
                            "flag": "🇩🇪"
                        })

                if len(news_items) >= 20:
                    break

            with open('bild.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            
            print(f"Gotovo! Bild skeniran, {len(news_items)} vijesti u džepu.")
            browser.close()

        except Exception as e:
            print(f"Greška: {e}")
            if 'browser' in locals():
                browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_bild()
