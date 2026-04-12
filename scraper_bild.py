import json
import sys
import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_title(title):
    if not title:
        return ""
    # Brišemo višestruke razmake i nepotrebne znakove na početku
    title = re.sub(r'\s+', ' ', title)
    title = re.sub(r'^[:\s–|-]+', '', title)
    # BildPlus oznake često smetaju, maknimo ih iz naslova
    title = title.replace("BILDplus", "").replace("BILD Plus", "")
    return title.strip()

def scrape_bild():
    url = "https://sportbild.bild.de/fussball/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Koristimo skroz svjež User Agent
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            print(f"Otvaram: {url}")
            # Čekamo da se učita barem nešto, ne čekamo cijeli DOM ako zapne
            page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Skrolamo malo više i čekamo da se sadržaj generira
            page.evaluate("window.scrollBy(0, 3000)")
            page.wait_for_timeout(5000) 
            
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            news_items = []
            
            # POKUŠAJ 1: Tražimo bilo koji link koji unutar sebe ima sliku i neki tekst (h2, h3, span)
            # Ovo je najsigurnija metoda kad klase stalno mijenjaju
            links = soup.find_all('a', href=True)

            for link_elem in links:
                # Tražimo naslov unutar linka ili odmah pored njega
                title_elem = link_elem.find(['h2', 'h3', 'span', 'p'], class_=re.compile(r'title|headline|text', re.I))
                if not title_elem:
                    # Ako nema specifičnu klasu, uzmi bilo koji h2/h3 unutar linka
                    title_elem = link_elem.find(['h2', 'h3'])
                
                img_elem = link_elem.find('img')

                if title_elem and img_elem:
                    raw_title = title_elem.get_text(" ", strip=True)
                    
                    if len(raw_title) < 12: # Preskoči prekratke (npr. "Menu", "Login")
                        continue
                        
                    title = clean_title(raw_title)
                    href = link_elem['href']
                    
                    if href.startswith('/'):
                        href = "https://sportbild.bild.de" + href
                    
                    # Izbjegavamo duplikate i ne-sportske linkove
                    if not any(item['title'] == title for item in news_items) and "/fussball/" in href:
                        
                        # Slike - pokušaj izvući najbolju kvalitetu
                        image = img_elem.get('src') or img_elem.get('data-src') or ""
                        if "1x1" in image or not image:
                            # Pokušaj naći srcset u blizini
                            parent = link_elem.parent
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

            # Ako je lista i dalje prazna, ispiši grešku za debug
            if not news_items:
                print("Upozorenje: Scraper nije pronašao ništa. Bild je vjerojatno promijenio strukturu.")
            else:
                with open('bild.json', 'w', encoding='utf-8') as f:
                    json.dump(news_items, f, ensure_ascii=False, indent=4)
                print(f"Uspješno spremljeno {len(news_items)} vijesti.")

            browser.close()

        except Exception as e:
            print(f"Greška: {e}")
            if 'browser' in locals():
                browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_bild()
