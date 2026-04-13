import json
import sys
import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_title(title):
    if not title:
        return ""
    
    # 1. Uzimamo samo prvu rečenicu (do . ! ili ?) 
    # To rješava problem onih dugačkih opisa iz Maksimira
    match = re.search(r'^[^.!?]+[.!?]', title)
    clean = match.group(0) if match else title
    
    # 2. Režemo kategorije koje su zalijepljene (npr. "TRANSFERIOdluka")
    # Tražimo spoj malog i velikog slova
    split_match = re.search(r'([a-zčćžšđ])([A-ZČĆŽŠĐ][a-zčćžšđ])', clean)
    if split_match:
        clean = clean[split_match.start() + 1:]

    # 3. Standardni separatori - uzimamo desnu stranu ako postoji ":" (kao na Bildu)
    if ": " in clean:
        clean = clean.split(": ")[-1]

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
            print(f"Otvaram: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # --- BILD STANDARD ZA SLIKE ---
            # Skrolamo dolje da pokrenemo učitavanje svih slika
            page.evaluate("window.scrollBy(0, 2000)")
            # Čekamo malo duže (3 sekunde) da se slike zapravo pojave u HTML-u
            page.wait_for_timeout(3000) 
            
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            news_items = []
            articles = soup.find_all('article')

            for art in articles:
                # Tražimo naslov preciznije (pazimo na spajanje teksta unutar tagova)
                title_container = art.find(['h2', 'h3', 'h4'])
                if not title_container:
                    continue
                
                link_elem = title_container.find('a', href=True) or art.find('a', href=True)
                
                if title_container and link_elem:
                    # Koristimo razmak (" ") pri spajanju teksta da se riječi ne slijepe
                    raw_title = title_container.get_text(" ", strip=True)
                    title = clean_title(raw_title)
                    
                    link = link_elem['href']
                    if link.startswith('/'):
                        link = "https://sportske.jutarnji.hr" + link
                    
                    # --- POBOLJŠANO PREUZIMANJE SLIKA ---
                    img_elem = art.find('img')
                    image = ""
                    if img_elem:
                        # Prioritet: data-src (lazy load), pa src
                        image = img_elem.get('data-src') or img_elem.get('src') or ""
                        
                        # Ako je u src-u neki sitni placeholder (pixel), probaj srcset
                        if "base64" in image or image.endswith('.gif'):
                            srcset = img_elem.get('data-srcset') or img_elem.get('srcset', '')
                            if srcset:
                                image = srcset.split(' ')[0]

                    if len(title) > 5:
                        # Izbjegavamo duplikate
                        if not any(item['title'] == title for item in news_items):
                            news_items.append({
                                "title": title,
                                "link": link,
                                "image": image
                            })

                if len(news_items) >= 20:
                    break

            with open('sportske.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            
            print(f"Uspješno spremljeno {len(news_items)} vijesti u sportske.json")
            browser.close()

        except Exception as e:
            print(f"Greška: {e}")
            if 'browser' in locals():
                browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_sn()
