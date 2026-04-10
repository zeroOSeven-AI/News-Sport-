import json
import sys
import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_title(title):
    if not title:
        return ""
    # ESPN često stavlja " - ESPN" ili slične sufikse na kraj naslova
    title = re.sub(r'\s*-\s*ESPN.*$', '', title, flags=re.IGNORECASE)
    # Čišćenje viška razmaka
    return title.strip()

def scrape_espn():
    # URL za svjetski nogomet
    url = "https://www.espn.com/soccer/"
    
    with sync_playwright() as p:
        # Pokrećemo preglednik
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            print(f"Otvaram ESPN: {url}")
            # ESPN zna biti spor, pa čekamo da se učita glavni sadržaj
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Skrolanje da se pokrenu slike (lazy-load)
            page.evaluate("window.scrollBy(0, 1500)")
            page.wait_for_timeout(2000) 
            
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            news_items = []
            
            # ESPN koristi 'section.contentItem' za svoje glavne vijesti
            articles = soup.select('section.contentItem, .contentItem__content')

            for art in articles:
                # Naslovi su obično u h1 ili h2 s određenim klasama
                title_elem = art.find(['h1', 'h2', 'h3'])
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if title_elem and link_elem:
                    raw_title = title_elem.get_text(strip=True)
                    
                    if len(raw_title) < 10: # Preskoči prekratke naslove (kategorije i sl.)
                        continue
                    
                    title = clean_title(raw_title)
                    link = link_elem['href']
                    
                    # Popravi link ako je relativan
                    if link.startswith('/'):
                        link = "https://www.espn.com" + link
                    
                    # ESPN slike su često u data-src ili src
                    image = ""
                    if img_elem:
                        image = img_elem.get('data-default-src') or img_elem.get('src') or ""
                    
                    # Filtriranje duplikata i nevažnih linkova
                    if not any(item['title'] == title for item in news_items) and "video" not in link:
                        news_items.append({
                            "title": title,
                            "link": link,
                            "image": image,
                            "source_title1": "ESPN",
                            "source_title2": "FOOTBALL",
                            "source_color": "#ff0021", # ESPN Crvena
                            "flag": "🇺🇸"
                        })

                if len(news_items) >= 20:
                    break

            # Spremanje u espn.json (možeš promijeniti ime u bild.json ako tvoj widget i dalje traži to ime)
            filename = 'espn.json'
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            
            print(f"Uspješno spremljeno {len(news_items)} vijesti u {filename}")
            browser.close()

        except Exception as e:
            print(f"Greška kod ESPN-a: {e}")
            if 'browser' in locals():
                browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_espn()
