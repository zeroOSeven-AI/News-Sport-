import json
import sys
import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_title(title):
    if not title:
        return ""
    # Mičemo " - ESPN" i slične sufikse
    title = re.sub(r'\s*-\s*ESPN.*$', '', title, flags=re.IGNORECASE)
    return title.strip()

def scrape_espn():
    url = "https://www.espn.com/soccer/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Postavljamo veći prozor da se više sadržaja učita odjednom
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 2000}
        )
        page = context.new_page()

        try:
            print(f"Otvaram ESPN Soccer...")
            page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Skrolanje da se pokrenu lazy-load slike (ključno za ESPN!)
            page.evaluate("window.scrollBy(0, 3000)")
            page.wait_for_timeout(3000) 
            
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            news_items = []
            
            # Hvatanje svih glavnih kontejnera s vijestima
            articles = soup.select('section.contentItem, .contentItem__content, .item-wrapper')

            for art in articles:
                title_elem = art.find(['h1', 'h2', 'h3'])
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if title_elem and link_elem:
                    raw_title = title_elem.get_text(strip=True).upper()
                    
                    # FILTRIRANJE: Preskoči kategorije koje kvare dizajn (kao na tvojoj slici)
                    blacklisted_titles = ["TOP HEADLINES", "MAN UNITED FOCUS", "LATEST", "MORE FROM ESPN"]
                    if any(x in raw_title for x in blacklisted_titles) or len(raw_title) < 12:
                        continue
                    
                    title = clean_title(title_elem.get_text(strip=True))
                    link = link_elem['href']
                    if link.startswith('/'):
                        link = "https://www.espn.com" + link
                    
                    # --- FIX ZA SLIKE ---
                    # ESPN često drži slike u data-src ili data-default-src dok se ne skrola
                    image = (img_elem.get('data-default-src') or 
                             img_elem.get('data-src') or 
                             img_elem.get('src') or "")
                    
                    # Ako je slika mala ili "placeholder" (1x1 pixel), probaj naći bolju u source tagu
                    if "1x1" in image or not image:
                        source_tag = art.find('source')
                        if source_tag:
                            image = source_tag.get('srcset', '').split(' ')[0]
                    
                    # Osiguraj da imamo puni URL slike
                    if image and image.startswith('/'):
                        image = "https://www.espn.com" + image
                    
                    # Dodajemo samo ako imamo naslov i ako nije video link (često nemaju slike)
                    if not any(item['title'] == title for item in news_items) and "/video/" not in link:
                        news_items.append({
                            "title": title,
                            "link": link,
                            "image": image,
                            "source_title1": "ESPN",
                            "source_title2": "FOOTBALL",
                            "source_color": "#ff0021",
                            "flag": "🇺🇸"
                        })

                if len(news_items) >= 15:
                    break

            # Spremanje (pazi da ti se i u Scriptableu URL slaže s ovim imenom)
            with open('espn.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            
            print(f"Uspješno spremljeno {len(news_items)} vijesti u espn.json")
            browser.close()

        except Exception as e:
            print(f"Greška: {e}")
            if 'browser' in locals():
                browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_espn()
