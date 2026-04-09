import json
import sys
import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_title(title):
    if not title:
        return ""
    
    # 1. Bild često spaja prednaslov i naslov bez razmaka (npr. "Italiener berichtenZukunft")
    # Tražimo mjesto gdje malo slovo dodiruje veliko i umećemo razmak, 
    # ali onda uzimamo samo drugi dio (pravi naslov)
    match = re.search(r'([a-zčćžšđ])([A-ZČĆŽŠĐ][a-zčćžšđ])', title)
    if match:
        # Uzimamo sve od tog drugog velikog slova do kraja
        title = title[match.start() + 1:]

    # 2. Čistimo od standardnih separatora ako su ostali na početku
    delimiters = [' - ', ' | ', ' / ', ':', '–']
    clean = title
    for d in delimiters:
        if d in clean:
            # Ako je separator na početku, uzmi ono nakon njega
            parts = clean.split(d)
            clean = parts[1] if len(parts) > 1 else parts[0]
            
    return clean.strip()

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
            
            # Skrolanje da se pokrene lazy-load za slike
            page.evaluate("window.scrollBy(0, 2000)")
            page.wait_for_timeout(3000) 
            
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            news_items = []
            articles = soup.find_all('article')

            for art in articles:
                # Bild drži pravi naslov često u klasi koja sadrži 'headline'
                # Prvo pokušavamo naći element koji je baš naslov
                title_elem = art.find(['h2', 'h3', 'h4'], class_=re.compile(r'headline|title', re.I))
                if not title_elem:
                    title_elem = art.find(['h2', 'h3', 'h4'])
                
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if title_elem and link_elem:
                    raw_title = title_elem.get_text(" ", strip=True) # Dodajemo razmak pri spajanju spanova
                    
                    if len(raw_title) < 5:
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
                        
                    if not image:
                        source_tag = art.find('source')
                        if source_tag:
                            image = source_tag.get('srcset', '').split(' ')[0]

                    if image and image.startswith('/'):
                        image = "https://sportbild.bild.de" + image
                    # --------------

                    # Izbjegavamo duplikate
                    if not any(item['title'] == title for item in news_items):
                        news_items.append({
                            "title": title,
                            "link": link,
                            "image": image
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
