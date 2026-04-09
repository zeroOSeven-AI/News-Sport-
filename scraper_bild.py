import json
import sys
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_title(title):
    # Popis simbola kojima portali obično odvajaju ime novinara ili kategoriju
    delimiters = [' - ', ' | ', ' / ', ':', '–']
    clean = title
    for d in delimiters:
        if d in clean:
            # Uzimamo samo prvi dio prije simbola
            clean = clean.split(d)[0]
    return clean.strip()

def scrape_bild():
    # Koristimo mobilnu verziju jer je lakša za scrapanje
    url = "https://m.sportbild.bild.de/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Postavljamo User-Agent da nas ne blokiraju
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1"
        )
        page = context.new_page()

        try:
            print(f"Otvaram: {url}")
            page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Skrolamo malo dolje da pokrenemo lazy loading slika
            page.evaluate("window.scrollBy(0, 1000)")
            page.wait_for_timeout(2000) 
            
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            news_items = []
            # Bild koristi 'article' ili 'div' s određenim klasama za vijesti
            articles = soup.find_all(['article', 'div'], class_=lambda x: x and 'entry' in x.lower() or 'card' in x.lower())
            
            # Ako gornji selektor ne nađe ništa, probaj širi zahvat
            if not articles:
                articles = soup.find_all('article')

            for art in articles:
                title_elem = art.find(['h2', 'h3', 'h4', 'span'], class_=lambda x: x and 'title' in x.lower()) or art.find(['h2', 'h3', 'h4'])
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if title_elem and link_elem:
                    raw_title = title_elem.get_text(strip=True)
                    if not raw_title: continue
                    
                    title = clean_title(raw_title)
                    
                    # Sređivanje linka
                    link = link_elem['href']
                    if link.startswith('/'):
                        link = "https://sportbild.bild.de" + link
                    elif not link.startswith('http'):
                        link = "https://sportbild.bild.de/" + link
                    
                    # LOGIKA ZA SLIKE (Rješava problem praznih slika)
                    image = ""
                    if img_elem:
                        # Redoslijed: data-src (lazy load), srcset (izvucimo prvu), src
                        data_src = img_elem.get('data-src')
                        srcset = img_elem.get('srcset')
                        src = img_elem.get('src')
                        
                        if data_src:
                            image = data_src
                        elif srcset:
                            # Uzimamo prvi URL iz srcset-a (obično najmanja ili prva dostupna slika)
                            image = srcset.split(',')[0].split(' ')[0]
                        else:
                            image = src or ""
                    
                    # Ako je slika i dalje relativna putanja
                    if image.startswith('/'):
                        image = "https://www.bild.de" + image

                    # Filtriramo prekratke naslove i duplikate
                    if len(title) > 5 and not any(item['title'] == title for item in news_items):
                        news_items.append({
                            "title": title,
                            "link": link,
                            "image": image
                        })

                if len(news_items) >= 20:
                    break

            # Spremanje u datoteku koju Scriptable očekuje
            with open('bild.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            
            print(f"Uspješno spremljeno {len(news_items)} vijesti u bild.json")
            browser.close()

        except Exception as e:
            print(f"Greška tijekom scrapanja: {e}")
            if 'browser' in locals():
                browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_bild()
