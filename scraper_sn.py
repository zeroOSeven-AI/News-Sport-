import json
import sys
import re
from playwright.sync_api import sync_playwright
from BeautifulSoup import BeautifulSoup

def clean_title(title):
    if not title:
        return ""
    
    # 1. Uzimamo samo prvu rečenicu (do prve točke, uskličnika ili upitnika)
    # Ovo eliminira dugačke opise koje scraper povuče
    match = re.search(r'^[^.!?]+[.!?]', title)
    clean = match.group(0) if match else title
    
    # 2. Standardni separatori
    delimiters = [' - ', ' | ', ' / ']
    for d in delimiters:
        if d in clean:
            clean = clean.split(d)[0]
            
    return clean.strip()

def scrape_sn():
    url = "https://sportske.jutarnji.hr/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-http2"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("article", timeout=15000)
            
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            news_items = []
            articles = soup.find_all('article')

            for art in articles:
                # TRAŽENJE NASLOVA:
                # Prvo tražimo naslovni element (h2, h3, h4)
                title_container = art.find(['h2', 'h3', 'h4'])
                if not title_container:
                    continue
                
                # KLJUČNA PROMJENA: Tražimo link UNUTAR naslovnog elementa
                # Tamo Jutarnji drži samo tekst naslova, a izvan toga je podnaslov
                link_elem = title_container.find('a', href=True) or art.find('a', href=True)
                
                if title_container and link_elem:
                    # Uzimamo tekst samo iz linka ako postoji, inače iz containera
                    actual_title_elem = title_container.find('a') or title_container
                    raw_title = actual_title_elem.get_text(strip=True)
                    
                    # Čistimo naslov od repova
                    title = clean_title(raw_title)
                    
                    link = link_elem['href']
                    if link.startswith('/'):
                        link = "https://sportske.jutarnji.hr" + link
                    
                    img_elem = art.find('img')
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
