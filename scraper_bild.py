import json
import sys
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_title(title):
    # Popis simbola kojima portali obično odvajaju ime novinara ili kategoriju
    delimiters = [' - ', ' | ', ' / ']
    clean = title
    for d in delimiters:
        if d in clean:
            # Uzimamo samo prvi dio prije simbola
            clean = clean.split(d)[0]
    return clean.strip()

def scrape_bild():
    url = "https://m.sportbild.bild.de/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            # Povećan timeout i dodan wait_until
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Mala pauza da se JS učita do kraja
            page.wait_for_timeout(2000) 
            
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            news_items = []
            articles = soup.find_all('article')

            for art in articles:
                title_elem = art.find(['h2', 'h3', 'h4', 'span'])
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if title_elem and link_elem:
                    raw_title = title_elem.get_text(strip=True)
                    title = clean_title(raw_title)
                    
                    link = link_elem['href']
                    if link.startswith('/'):
                        link = "https://m.sportbild.bild.de" + link
                    
                    image = ""
                    if img_elem:
                        # Bild često koristi 'src' ili 'srcset'
                        image = img_elem.get('src') or img_elem.get('data-src') or ""
                    
                    if len(title) > 5:
                        news_items.append({
                            "title": title,
                            "link": link,
                            "image": image
                        })

                if len(news_items) >= 20:
                    break

            # Spremanje u JSON
            with open('sportske.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            
            print(f"Uspješno spremljeno {len(news_items)} vijesti u sportske.json")
            browser.close()

        except Exception as e:
            print(f"Greška tijekom scrapanja: {e}")
            browser.close()
            sys.exit(1)

if __name__ == "__main__":
    # Ovdje je bila greška - sada se zove scrape_bild() kao i gore definirana funkcija
    scrape_bild()
