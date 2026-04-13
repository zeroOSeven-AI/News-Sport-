import json
import sys
import re
import time
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def scrape_sn():
    url = "https://sportske.jutarnji.hr/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            print(f"Otvaram: {url}")
            # Čekamo da se mreža smiri
            page.goto(url, wait_until="networkidle", timeout=60000)

            # --- SMART SCROLL: Probuđujemo slike da dobijemo rezoluciju ---
            print("Učitavam slike i mjerim dimenzije...")
            page.evaluate("""async () => {
                await new Promise((resolve) => {
                    let totalHeight = 0;
                    let distance = 250;
                    let timer = setInterval(() => {
                        let scrollHeight = document.body.scrollHeight;
                        window.scrollBy(0, distance);
                        totalHeight += distance;
                        // Skrolaj do 4000px visine, to je obično dovoljno za prvih 20 vijesti
                        if(totalHeight >= 4000 || totalHeight >= scrollHeight){
                            clearInterval(timer);
                            resolve();
                        }
                    }, 100);
                });
            }""")
            
            # Mala pauza da se browser "smiri" nakon skrolanja
            time.sleep(2)

            # Izvlačimo mapu slika i njihovih prirodnih dimenzija direktno iz browsera
            img_dims = page.evaluate("""() => {
                let dims = {};
                document.querySelectorAll('img').forEach(img => {
                    // Uzimamo currentSrc jer je to stvarni URL koji je browser odabrao
                    let src = img.currentSrc || img.src;
                    if (src && img.naturalWidth > 0) {
                        dims[src] = { w: img.naturalWidth, h: img.naturalHeight };
                    }
                });
                return dims;
            }""")
            
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            news_items = []
            articles = soup.find_all('article')

            for art in articles:
                title_elem = art.find(['h2', 'h3', 'h4'])
                link_elem = art.find('a', href=True)
                img_elem = art.find('img')

                if title_elem and link_elem:
                    # Čišćenje kickera (kategorije) iz naslova
                    kicker = title_elem.find(['span', 'b', 'i'])
                    full_text = title_elem.get_text(separator=" ", strip=True)
                    if kicker:
                        kicker_text = kicker.get_text(strip=True)
                        title = full_text.replace(kicker_text, "").strip()
                    else:
                        title = full_text
                    
                    if len(title) < 15: title = full_text
                    title = re.sub(r'^[:\s–|-]+', '', title).strip()
                    
                    link = link_elem['href']
                    if link.startswith('/'):
                        link = "https://sportske.jutarnji.hr" + link
                    
                    # Logika za sliku i njezinu rezoluciju
                    image = ""
                    width = 0
                    height = 0
                    
                    if img_elem:
                        # Prioritet: currentSrc (ono što browser vidi), pa data-src, pa src
                        image = (img_elem.get('currentSrc') or img_elem.get('data-src') or img_elem.get('src') or "")
                    
                    if not image or "base64" in image:
                        source_tag = art.find('source')
                        if source_tag:
                            image = source_tag.get('srcset', '').split(' ')[0]

                    if image and image.startswith('/'):
                        image = "https://sportske.jutarnji.hr" + image

                    # Sparivanje s izmjerenim dimenzijama
                    if image in img_dims:
                        width = img_dims[image]['w']
                        height = img_dims[image]['h']
                    else:
                        # Ako nema savršenog matcha, probaj naći sličan URL (fuzzy match)
                        for key in img_dims:
                            if image and (image in key or key in image):
                                width = img_dims[key]['w']
                                height = img_dims[key]['h']
                                break

                    if not any(item['title'] == title for item in news_items):
                        news_items.append({
                            "title": title,
                            "link": link,
                            "image": image,
                            "width": width,
                            "height": height,
                            "ratio": round(width / height, 2) if height > 0 else 0
                        })

                if len(news_items) >= 20:
                    break

            with open('sportske.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)
            
            print(f"Uspješno spremljeno {len(news_items)} vijesti s rezolucijama.")
            browser.close()

        except Exception as e:
            print(f"Greška: {e}")
            if 'browser' in locals():
                browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_sn()
