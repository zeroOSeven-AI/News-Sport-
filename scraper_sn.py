import json
import sys
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_title(title):
    delimiters = [' - ', ' | ', ' / ']
    clean = title
    for d in delimiters:
        if d in clean:
            clean = clean.split(d)[0]
    return clean.strip()

def scrape_sn():
    url = "https://sportske.jutarnji.hr/"
    
    with sync_playwright() as p:
        # Dodao sam 'args' da izbjegnemo probleme u Docker/CI okruženjima
        browser = p.chromium.launch(headless=True, args=["--disable-http2"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            # PROMJENA: Koristimo 'domcontentloaded' umjesto 'networkidle'
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Dodatna sigurnost: čekamo da se bar jedan članak pojavi na stranici
            page.wait_for_selector("article", timeout=15000)
            
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            news_items = []
            articles = soup.find_all('article')

            for art in articles:
                title_elem = art.find(['h2', 'h3', 'h4', 'span']) # Jutarnji nekad koristi span za naslove
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if title_elem and link_elem:
                    raw_title = title_elem.get_text(strip=True)
                    title = clean_title(raw_title)
                    
                    link = link_elem['href']
                    if link.startswith('/'):
                        link = "https://sportske.jutarnji.hr" + link
                    
                    # Provjera za slike (Jutarnji često koristi lazy loading)
                    image = ""
                    if img_elem:
                        image = img_elem.get('data-src') or img_elem.get('src') or img_elem.get('data-srcset') or ""
                    
                    if len(title) > 5:
                        news_items.append({
                            "title": title,
                            "link": link,
                            "image": image
                        })

                if len(news_items) >= 20:
                    break

            with open('sportske.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            
            print(f"Uspješno spremljeno {len(news_items)} vijesti.")
            browser.close()

        except Exception as e:
            print(f"Greška: {e}")
            if 'browser' in locals():
                browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_sn()
