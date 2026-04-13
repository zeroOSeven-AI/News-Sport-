def clean_title(title):
    if not title:
        return ""
    
    # 1. Bild spoji nadnaslov i naslov (npr. "BaumannJeder hat...")
    # Samo umetni razmak da možemo lakše baratati tekstom
    title = re.sub(r'([a-zčćžšđ])([A-ZČĆŽŠĐ])', r'\1 \2', title)

    # 2. EKSTREMNO ČIŠĆENJE: 
    # Ako imamo razmak, uzmi samo ono ŠTO SLIJEDI nakon prve riječi.
    # Tako "Debatte um DFB-Tor : Baumann..." postaje samo "Baumann..."
    if " : " in title:
        parts = title.split(" : ", 1)
        title = parts[1]
    elif " " in title:
        # Ako nema dvotočke, ali ima više riječi, probaj maknuti samo prvu 
        # (to je obično onaj jedan "Kicker" nadnaslov)
        parts = title.split(' ', 1)
        if len(parts) > 1:
            title = parts[1]
            
    # 3. Finalno glancanje
    title = re.sub(r'^[:\s–|-]+', '', title)
    return title.strip()
