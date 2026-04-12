import json
import sys
import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_title(title):
    if not title: return ""
    # Bild često stavlja "BILDplus" ili "Video" u naslov, to nam ne treba
    title = re.sub(r'BILDplus|Video|O-Ton', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+', ' ', title)
    return title.strip()

def scrape_bild():
    # Idemo direktno na mobilnu verziju jer je lakša za scrapanje, ali s desktop agentom
    url = "https://sportbild.bild.de/fussball/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Postavljamo vrlo specifičan context da izgledamo kao pravi Chrome na Windowsima
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()

        try:
            print(f"Otvaram: {url}")
            # Povećavamo timeout i čekamo da se učita "domcontentloaded"
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
            
            # Čekamo malo da se JS izvrši
            page.wait_for_timeout(5000)
            
            # Skrolamo polako u par navrata da "prevarimo" detekciju bota
            for _ in range(3):
                page.evaluate("window.scrollBy(0, 800)")
                page.wait_for_timeout(1000)
            
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            news_items = []
            
            # Bild na naslovnici koristi ove klases za vijesti
            # Tražimo 'article' tagove ili 'div' elemente koji glume artikle
            articles = soup.select('article, .story, .teaser, [data-component="teaser"]')

            for art in articles:
                # Bild naslov se obično nalazi unutar klase koja sadrži 'headline' ili 'title'
                title_elem = art.select_one('h2, h3, .headline, .title')
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if title_elem and link_elem:
                    # Hvatanje punog naslova (Kicker + Headline)
                    raw_title = title_elem.get_text(" ", strip=True)
                    
                    if len(raw_title) < 15: continue
                    
                    title = clean_title(raw_title)
                    href = link_elem['href']
                    if href.startswith('/'):
                        href = "https://sportbild.bild.de" + href
                    
                    # Izbjegavamo duplikate
                    if any(item['title'] == title for item in news_items):
                        continue

                    # Slika - Bild koristi 'data-src' za lazy load
                    image = img_elem.get('data-src') or img_elem.get('src') or ""
                    
                    # Ako je slika neka placeholder ikona (obično mala), tražimo dalje
                    if not image or "1x1" in image or "data:image" in image:
                        # Tražimo u source tagovima u blizini
                        parent = art.find('picture') or art
                        source = parent.find('source')
                        if source:
                            image = source.get('srcset', '').split(' ')[0]

                    if image and image.startswith('/'):
                        image = "https://sportbild.bild.de" + image

                    news_items.append({
                        "title": title,
                        "link": href,
                        "image": image,
                        "source_title1": "SPORT",
                        "source_title2": "BILD",
                        "source_color": "#e20613",
                        "flag": "🇩🇪"
                    })

                if len(news_items) >= 20:
                    break

            if not news_items:
                # Zadnji pokušaj: ako ništa nismo našli, ispiši soup da vidimo što vidi scraper
                print("Ništa nije pronađeno. Provjeravam alternativne tagove...")
                # Alternativni selektor za naslove ako su promijenili klase
                titles = soup.find_all(['h2', 'h3'])
                print(f"Pronađeno {len(titles)} H2/H3 tagova ukupno.")

            with open('bild.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            
            print(f"Gotovo! Spremljeno {len(news_items)} vijesti.")
            browser.close()

        except Exception as e:
            print(f"Greška: {e}")
            if 'browser' in locals():
                browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_bild()
