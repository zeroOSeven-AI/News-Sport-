import json
import sys
import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_title(title):
    if not title: return ""
    # Marca zna imati čudne znakove na početku/kraju
    return title.strip()

def scrape_marca():
    # Engleska verzija Marce (čišći naslovi za widget)
    url = "https://www.marca.com/en/football.html"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 2000}
        )
        page = context.new_page()

        try:
            print(f"Napad na Marcu počeo... Scraper ulazi u bazu.")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Pauza za 'cigaru' - Marca ima puno skripti koje nas prate
            page.wait_for_timeout(7000) 
            
            # Skrolanje je kod Marce KLJUČNO jer su im slike 'skrivene' duboko
            for i in range(3):
                page.evaluate(f"window.scrollBy(0, 800)")
                page.wait_for_timeout(1500)
            
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            news_items = []
            
            # Marca koristi 'article' tagove za skoro sve
            articles = soup.find_all('article')

            for art in articles:
                # Naslovi su kod Marce obično u h2 ili h3 klasama
                title_elem = art.find(['h2', 'h3', 'header'])
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if title_elem and link_elem:
                    title = clean_title(title_elem.get_text(strip=True))
                    
                    # Izbacujemo premale naslove i reklame
                    if len(title) < 15 or "Subscribe" in title:
                        continue
                        
                    link = link_elem['href']
                    # Popravi link ako je relativan
                    if link.startswith('//'): link = "https:" + link
                    elif link.startswith('/'): link = "https://www.marca.com" + link
                    
                    # --- MARCA SLIKA FIX ---
                    image = ""
                    if img_elem:
                        # Marca koristi 'data-src' ili 'src' ovisno o poziciji na ekranu
                        image = (img_elem.get('data-src') or 
                                 img_elem.get('src') or "")
                    
                    # Ako je i dalje prazno, tražimo u 'picture' tagu
                    if not image or "pixel" in image:
                        pic_tag = art.find('picture')
                        if pic_tag:
                            source = pic_tag.find('source')
                            if source:
                                image = source.get('srcset', '').split(' ')[0]

                    # Neke slike na Marci počinju s //
                    if image.startswith('//'): image = "https:" + image

                    if not any(item['title'] == title for item in news_items):
                        news_items.append({
                            "title": title,
                            "link": link,
                            "image": image,
                            "source_title1": "MARCA",
                            "source_title2": "FOOTBALL",
                            "source_color": "#ff4b00", # Marca narančasto-crvena
                            "flag": "🇪🇸"
                        })

                if len(news_items) >= 15:
                    break

            # Spremanje (možeš nazvati espn.json ako želiš da widget samo to povuče)
            with open('marca.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            
            print(f"Pobjeda! Marca pala, {len(news_items)} vijesti u džepu.")
            browser.close()

        except Exception as e:
            print(f"Greška u napadu: {e}")
            if 'browser' in locals():
                browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_marca()
