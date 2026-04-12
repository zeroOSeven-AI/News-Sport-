import json
import sys
import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_title(title):
    if not title:
        return ""
    title = re.sub(r'\s*-\s*ESPN.*$', '', title, flags=re.IGNORECASE)
    return title.strip()

def scrape_espn():
    url = "https://www.espn.com/soccer/"
    
    with sync_playwright() as p:
        # Pokrećemo chromium
        browser = p.chromium.launch(headless=True)
        
        # Postavljamo kontekst da izgledamo kao pravi korisnik koji je došao s Googlea
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.google.com/"
            },
            viewport={'width': 1280, 'height': 2000}
        )
        
        page = context.new_page()

        try:
            print(f"Otvaram ESPN... Scraper je sjeo, pali cigaru i čeka.")
            
            # Ne čekamo networkidle jer nas to jebe (timeout), samo osnovni DOM
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # --- "ZAPALI CIGARU" (FIXNA PAUZA) ---
            # Dajemo stranici 8 sekundi da se smiri i učita skripte u pozadini
            page.wait_for_timeout(8000) 
            
            print("Skrola lagano niz stranicu...")
            # Skrolamo dva puta po malo da okinemo lazy-load slika
            page.evaluate("window.scrollBy(0, 1000)")
            page.wait_for_timeout(2000)
            page.evaluate("window.scrollBy(0, 1000)")
            page.wait_for_timeout(2000)
            
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            news_items = []
            
            # Ciljamo kontejnere koji imaju i sliku i tekst
            articles = soup.select('section.contentItem, .contentItem__content, .item-wrapper, article')

            for art in articles:
                title_elem = art.find(['h1', 'h2', 'h3'])
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if title_elem and link_elem:
                    raw_title = title_elem.get_text(strip=True)
                    raw_title_upper = raw_title.upper()
                    
                    # Izbacujemo smeće i kategorije bez pravih vijesti
                    blacklisted = ["TOP HEADLINES", "MAN UNITED FOCUS", "LATEST", "MORE FROM ESPN", "SCORES"]
                    if any(x in raw_title_upper for x in blacklisted) or len(raw_title) < 15:
                        continue
                    
                    title = clean_title(raw_title)
                    link = link_elem['href']
                    if link.startswith('/'):
                        link = "https://www.espn.com" + link
                    
                    # --- AGRESIVNO HVATANJE SLIKE ---
                    image = ""
                    if img_elem:
                        # ESPN rotira ove atribute ovisno o tome jesu li učitani
                        image = (img_elem.get('data-default-src') or 
                                 img_elem.get('data-src') or 
                                 img_elem.get('src') or "")
                    
                    # Ako je slika onaj prozirni 1x1 pixel, traži u source tagu
                    if "1x1" in image or not image:
                        source_tag = art.find('source')
                        if source_tag:
                            image = source_tag.get('srcset', '').split(' ')[0]

                    # Popravi relativne putanje
                    if image and image.startswith('/'):
                        image = "https://www.espn.com" + image
                    
                    # Nećemo video linkove jer oni često nemaju thumbnail koji možemo lako izvući
                    if not any(item['title'] == title for item in news_items) and "/video/" not in link:
                        news_items.append({
                            "title": title,
                            "link": link,
                            "image": image,
                            "source_title1": "ESPN",
                            "source_title2": "FOOTBALL",
                            "source_color": "#ff0021",
                            "flag": "🇺🇸"
                        })

                if len(news_items) >= 15:
                    break

            with open('espn.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            
            print(f"Gotovo! Spremljeno {len(news_items)} vijesti. Scraper je popušio svoje.")
            browser.close()

        except Exception as e:
            print(f"Greška: {e}")
            if 'browser' in locals():
                browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_espn()
