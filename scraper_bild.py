import json
import sys
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_title(title):
    # Čistimo naslov od nepotrebnih prefiksa i simbola
    delimiters = [' - ', ' | ', ' / ', ':', '–']
    clean = title
    for d in delimiters:
        if d in clean:
            clean = clean.split(d)[0]
    return clean.strip()

def scrape_bild():
    url = "https://m.sportbild.bild.de/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Koristimo iPhone User-Agent jer mobilna verzija lakše servira slike
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
        )
        page = context.new_page()

        try:
            print(f"Otvaram: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # KLJUČNO ZA SLIKE: Skrolanje i čekanje da se lazy-load slike učitaju
            page.evaluate("window.scrollBy(0, 1500)")
            page.wait_for_timeout(4000) 
            
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            news_items = []
            
            # Tražimo sve article elemente
            articles = soup.find_all('article')

            for art in articles:
                # Naslov može biti u različitim tagovima ovisno o sekciji
                title_elem = art.find(['h2', 'h3', 'h4', 'span'], class_=lambda x: x is not None and 'title' in x.lower())
                if not title_elem:
                    title_elem = art.find(['h2', 'h3', 'h4'])
                
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if title_elem and link_elem:
                    raw_title = title_elem.get_text(strip=True)
                    if len(raw_title) < 5:
                        continue
                    
                    title = clean_title(raw_title)
                    
                    link = link_elem['href']
                    if link.startswith('/'):
                        link = "https://sportbild.bild.de" + link
                    
                    # --- POPRAVAK ZA SLIKE ---
                    image = ""
                    if img_elem:
                        # Prioritet: data-src -> srcset -> src
                        # Bild često drži pravu sliku u data-src zbog lazy loadinga
                        image = (img_elem.get('data-src') or 
                                 img_elem.get('srcset', '').split(' ')[0] or 
                                 img_elem.get('src') or "")
                    
                    # Ako je slika i dalje prazna, probaj naći unutar picture taga
                    if not image:
                        pic_tag = art.find('source')
                        if pic_tag:
                            image = pic_tag.get('srcset', '').split(' ')[0]

                    if image and image.startswith('/'):
                        image = "https://www.bild.de" + image
                    # -------------------------

                    if not any(item['title'] == title for item in news_items):
                        news_items.append({
                            "title": title,
                            "link": link,
                            "image": image
                        })

                if len(news_items) >= 20:
                    break

            # Spremanje u bild.json (pazi da ti se i u YAML-u zove tako!)
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
