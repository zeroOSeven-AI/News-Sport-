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
            page.goto(url, wait_until="networkidle", timeout=60000)

            # --- FORCE LOAD SLIKA ---
            # Skrolamo i čekamo da preglednik prijavi da su slike učitane
            print("Forsiram učitavanje slika...")
            page.evaluate("""async () => {
                const delay = ms => new Promise(res => setTimeout(res, ms));
                for (let i = 0; i < 10; i++) {
                    window.scrollBy(0, 500);
                    await delay(200);
                }
                // Čekamo da se sve slike koje su u DOM-u učitaju (decoded)
                const imgs = Array.from(document.querySelectorAll('article img'));
                const promises = imgs.map(img => {
                    if (img.complete) return Promise.resolve();
                    return new Promise(resolve => { 
                        img.onload = resolve; 
                        img.onerror = resolve; 
                    });
                });
                await Promise.all(promises);
            }""")
            
            # Pauza za svaki slučaj
            time.sleep(1)

            # Direktno izvlačenje podataka o vijestima iz preglednika (JS je ovdje precizniji od BeautifulSoup-a)
            # Ovim izbjegavamo neslaganje URL-ova između BS4 i JS-a
            news_data = page.evaluate("""() => {
                let results = [];
                let articles = document.querySelectorAll('article');
                
                articles.forEach(art => {
                    let titleElem = art.querySelector('h2, h3, h4');
                    let linkElem = art.querySelector('a');
                    let imgElem = art.querySelector('img');
                    
                    if (titleElem && linkElem) {
                        let title = titleElem.innerText.trim();
                        let link = linkElem.href;
                        let imgUrl = imgElem ? (imgElem.currentSrc || imgElem.src) : "";
                        let w = imgElem ? imgElem.naturalWidth : 0;
                        let h = imgElem ? imgElem.naturalHeight : 0;
                        
                        results.append({
                            title: title,
                            link: link,
                            image: imgUrl,
                            width: w,
                            height: h
                        });
                    }
                });
                return results;
            }""")
            
            # Čišćenje naslova (uklanjanje kickera)
            clean_items = []
            for item in news_data:
                # Sportske često imaju naslov spojen s kategorijom, npr "NOGOMET Dinamo melje..."
                # Ovdje koristimo regex da očistimo naslov ako je potrebno
                raw_title = item['title']
                # Ako želiš dodatno čišćenje naslova, možeš ovdje, ali JS innerText obično odradi dobar posao
                
                if not any(x['title'] == raw_title for x in clean_items):
                    w = item['width']
                    h = item['height']
                    clean_items.append({
                        "title": raw_title,
                        "link": item['link'],
                        "image": item['image'],
                        "width": w,
                        "height": h,
                        "ratio": round(w / h, 2) if h > 0 else 0
                    })
                
                if len(clean_items) >= 25: break

            with open('sportske.json', 'w', encoding='utf-8') as f:
                json.dump(clean_items, f, ensure_ascii=False, indent=4)
            
            print(f"Uspješno spremljeno {len(clean_items)} vijesti. Provjeri JSON!")
            browser.close()

        except Exception as e:
            print(f"Greška: {e}")
            if 'browser' in locals(): browser.close()
            sys.exit(1)

if __name__ == "__main__":
    scrape_sn()
