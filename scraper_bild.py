import json
import sys
import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_title(title):
    if not title:
        return ""
    
    # Mičemo višestruke razmake koji nastaju spajanjem elemenata
    title = re.sub(r'\s+', ' ', title)
    
    # Čistimo od viška na početku ako je ostalo nešto tipa ": Naslov"
    title = re.sub(r'^[:\s–|-]+', '', title)
    
    return title.strip()

def scrape_bild():
    # Koristimo desktop verziju jer mobilna zna imati još agresivnije skraćene naslove
    url = "https://sportbild.bild.de/fussball/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
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
            # Bild na desktopu često koristi 'article' ili specifične klase
            articles = soup.find_all(['article', 'div'], class_=re.compile(r'story|teaser', re.I))

            for art in articles:
                # TRAŽENJE NASLOVA: Ciljamo element koji sadrži i Kicker i Headline
                # Bild obično drži oba unutar h2 ili h3 taga
                title_container = art.find(['h2', 'h3', 'h4'])
                
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if title_container and link_elem:
                    # Trik: uzimamo sav tekst unutar naslova, ali pazimo na razmake
                    # To spaja "Baumann" i "Jeder hat seinen Senf..." u jednu smislenu rečenicu
                    raw_title = title_container.get_text(": ", strip=True) 
                    
                    # Ako je naslov ispao samo broj ili nešto prekratko, preskačemo
                    if len(raw_title) < 10:
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
                    
                    # Popravak za male 1x1 pixele
                    if not image or "1x1" in image:
                        source_tag = art.find('source')
                        if source_tag:
                            image = source_tag.get('srcset', '').split(' ')[0]

                    if image and image.startswith('/'):
                        image = "https://sportbild.bild.de" + image
                    # --------------

                    # Izbjegavamo duplikate i smeće
                    if not any(item['title'] == title for item in news_items) and "bildplus" not in link.lower():
                        news_items.append({
                            "title": title,
                            "link": link,
                            "image": image,
                            "source_title1": "SPORT",
                            "source_title2": "BILD",
                            "source_color": "#e20613",
                            "flag": "🇩🇪"
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
