import json
import sys
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def scrape_sn():
    # Direktna adresa sportske rubrike
    url = "https://sportske.jutarnji.hr/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Simuliramo običan desktop browser
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            print(f"Otvaram: {url}")
            page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Uzimamo HTML i šaljemo ga u BeautifulSoup
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            news_items = []
            # Sportske koriste <article> za svaku vijest
            articles = soup.find_all('article')

            for art in articles:
                # Tražimo naslov i link
                title_elem = art.find(['h2', 'h3', 'h4'])
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if title_elem and link_elem:
                    title = title_elem.get_text(strip=True)
                    link = link_elem['href']
                    
                    if link.startswith('/'):
                        link = "https://sportske.jutarnji.hr" + link
                    
                    # Hvatanje slike (provjera više mogućih atributa zbog lazy-loadinga)
                    image = ""
                    if img_elem:
                        image = img_elem.get('data-src') or img_elem.get('src') or ""
                        # Ako je slika samo transparentni pixel, preskoči
                        if "base64" in image or "empty.png" in image:
                            image = img_elem.get('data-srcset') or ""
                    
                    if len(title) > 5:
                        news_items.append({
                            "title": title,
                            "link": link,
                            "image": image
                        })

                if len(news_items) >= 20:
                    break

            if not news_items:
                print("Nije pronađena nijedna vijest.")
                sys.exit(1)

            # Spremanje u JSON
            with open('sportske.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            
            print(f"Uspješno spremljeno {len(news_items)} vijesti u sportske.json")
            browser.close()

        except Exception as e:
            print(f"Greška: {e}")
            sys.exit(1)

if __name__ == "__main__":
    scrape_sn()
