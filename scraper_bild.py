import json
import sys
import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_title(title):
    if not title: return ""
    # Bild zna imati čudne prefikse poput "BILDplus" ili "KOMENTAR"
    title = re.sub(r'^(BILDplus|KOMENTAR|VIDEO|FOTOS)\s*', '', title, flags=re.IGNORECASE)
    return title.strip()

def scrape_bild():
    # Mobilna verzija je često lakša za scrapanje jer ima manje smeća
    url = "https://m.bild.de/sport/fussball/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
            viewport={'width': 390, 'height': 844}
        )
        page = context.new_page()

        try:
            print(f"Ulazimo u Bild bazu... Scraper pali cigaru.")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Pauza da se učitaju njihovi dinamički naslovi
            page.wait_for_timeout(7000) 
            
            # Skrolanje je obavezno jer Bild ne učitava slike dok nisu blizu ekrana
            for _ in range(3):
                page.evaluate("window.scrollBy(0, 800)")
                page.wait_for_timeout(1500)
            
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            news_items = []
            
            # Bildove vijesti su obično u 'article' ili 'div' s klasama koje sadrže 'teaser'
            articles = soup.select('article, div[class*="teaser"]')

            for art in articles:
                # Naslov je kod Bilda često duboko u h2/h3 ili u klasi 'headline'
                title_elem = art.find(['h2', 'h3', 'span'], class_=re.compile(r'headline|title|text', re.I))
                link_elem = art.find('a', href=True)
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
                        # Bild koristi srcset ili data-src za visoku rezoluciju
                        image = (img_elem.get('data-src') or 
                                 img_elem.get('src') or "")
                    
                    # Ako je slika placeholder, tražimo u 'source' tagovima
                    if not image or "1x1" in image or "data:image" in image:
                        source_tag = art.find('source')
                        if source_tag:
                            # Uzimamo prvi URL iz srcset-a
                            srcset = source_tag.get('srcset', '')
                            if srcset:
                                image = srcset.split(',')[0].split(' ')[0]

                    # Čišćenje URL-a slike (neki imaju parametre za širinu na kraju)
                    if image and not image.startswith('http'):
                        if image.startswith('//'): image = "https:" + image
                        else: image = "https://www.bild.de" + image

                    if not any(item['title'] == title for item in news_items):
                        news_items.append({
                            "title": title,
                            "link": link,
                            "image": image,
                            "source_title1": "BILD",
                            "source_title2": "SPORT",
                            "source_color": "#fc4e4e", # Bild crvena
                            "flag": "🇩🇪"
                        })

                if len(news_items) >= 15:
                    break

            # Spremanje u bild.json
            with open('bild.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            
            print(f"Gotovo! Bild je skeniran, {len(news_items)} vijesti spremno.")
            browser.close()

        except Exception as e:
            print(f"Greška kod Bilda: {e}")
            if 'browser' in locals():
                browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_bild()
