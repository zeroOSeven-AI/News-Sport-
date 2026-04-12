import json
import sys
import re
from playwright.sync_api import sync_playwright

def clean_title(title):
    if not title:
        return ""
    # Mičemo ESPN sufikse i čistimo nepotrebne razmake
    title = re.sub(r'\s*-\s*ESPN.*$', '', title, flags=re.IGNORECASE)
    return title.strip()

def scrape_espn():
    # Koristimo API endpoint za nogometne vijesti umjesto cijele web stranice
    api_url = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/news?limit=50"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        
        page = context.new_page()

        try:
            print(f"Pristupam ESPN API-ju... Nema cigare, ovo ide brzo!")
            
            # API vraća čisti JSON, pa nam BeautifulSoup više ne treba
            page.goto(api_url, timeout=60000)
            content = page.locator("pre").inner_text() # Playwright često JSON prikaže unutar <pre> taga
            
            data = json.loads(content)
            articles = data.get('articles', [])
            
            news_items = []

            for art in articles:
                # API nam daje točno ono što trebamo bez nagađanja
                raw_title = art.get('headline', '')
                link = art.get('links', {}).get('web', {}).get('href', '')
                
                # Slike u API-ju su u listi, uzimamo prvu dostupnu
                images = art.get('images', [])
                image = images[0].get('url', '') if images else ""

                if raw_title and link:
                    title = clean_title(raw_title)
                    
                    # Izbacujemo prekratke naslove (često su to samo kategorije)
                    if len(title) < 15:
                        continue
                    
                    # Provjera duplikata i video linkova (isto kao u tvom kodu)
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

            # Spremanje u espn.json
            with open('espn.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            
            print(f"Gotovo! Spremljeno {len(news_items)} čistih vijesti.")
            browser.close()

        except Exception as e:
            print(f"Greška: {e}")
            if 'browser' in locals():
                browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_espn()
