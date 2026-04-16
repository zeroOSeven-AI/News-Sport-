def scrape_bild():
    url = "https://m.sportbild.bild.de/"
    # Lista riječi koje želimo izbjeći u URL-u slike
    forbidden_words = ["ticker", "banner", "bitter", "score", "overlay"]
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)",
            viewport={'width': 390, 'height': 844}
        )
        page = context.new_page()

        try:
            print(f"🚀 Scraping Bild (Clean Image mode)...")
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.evaluate("window.scrollBy(0, 2000)")
            time.sleep(2)

            soup = BeautifulSoup(page.content(), 'html.parser')
            news_items = []
            articles = soup.find_all('article')

            for art in articles:
                title_elem = art.find(['h2','h3','h4'])
                link_elem = art.find('a', href=True)
                # Nađi sve slike unutar artikla, ne samo prvu
                all_imgs = art.find_all('img')

                if title_elem and link_elem and all_imgs:
                    title = title_elem.get_text(strip=True)
                    title = re.sub(r'^[:\s–|-]+', '', title).strip()
                    
                    link = link_elem['href']
                    if link.startswith('/'): link = "https://sportbild.bild.de" + link

                    # LOGIKA ZA ODABIR ČISTE SLIKE
                    img_url = None
                    for img in all_imgs:
                        temp_url = img.get('data-src') or img.get('src')
                        if not temp_url: continue
                        
                        # Provjeri je li slika banner/ticker
                        is_clean = not any(word in temp_url.lower() for word in forbidden_words)
                        
                        if is_clean:
                            img_url = temp_url
                            break # Našli smo dobru sliku, stani
                    
                    # Ako nismo našli "čistu", a imamo bar neku, uzmi prvu (fallback)
                    if not img_url:
                        img_url = all_imgs[0].get('data-src') or all_imgs[0].get('src')

                    if img_url and img_url.startswith('/'): 
                        img_url = "https://sportbild.bild.de" + img_url

                    info = get_image_info(img_url)
                    if info:
                        print(f"✅ Dodano: {title[:30]}...")
                        news_items.append({
                            "title": title,
                            "link": link,
                            "image_url": info["url"],
                            "w": info["w"],
                            "h": info["h"],
                            "focus_y": info["focus_y"],
                            "source_title1": "SPORT",
                            "source_title2": "BILD",
                            "source_color": "#fc4e4e",
                            "flag": "🇩🇪"
                        })

                if len(news_items) >= 20: break

            with open('bild.json', 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=4)

            print(f"✅ JSON spreman s filtriranim slikama.")
            browser.close()

        except Exception as e:
            print("❌ Greška:", e)
            browser.close()
