import streamlit as st
import pandas as pd
import urllib.request
import json
import re
import time
import ssl
from io import BytesIO
from datetime import datetime

# =============================================================================
# CONFIGURATION
# =============================================================================

st.set_page_config(page_title="DS Stock Europe", page_icon="🚗", layout="wide")

MODERN_SITES = {
    'FRANCE': { 'url': "https://store.dsautomobiles.fr", 'lat': "46.2276", 'lon': "2.2137" },
    'ESPAGNE': { 'url': "https://store.dsautomobiles.es", 'lat': "40.4168", 'lon': "-3.7038" },
    'ITALIE': { 'url': "https://store.dsautomobiles.it", 'lat': "41.9028", 'lon': "12.4964" }
}

LEGACY_SITES = {
    'ROYAUME-UNI': "https://www.stellantisandyou.co.uk/ds/new-cars-in-stock",
    'POLOGNE': "https://sklep.dsautomobiles.pl/",
    'PORTUGAL': "https://dsonlinestore.dsautomobiles.pt/listagem", 
    'PAYS-BAS': "https://voorraad.dsautomobiles.nl/stock",
    'BELGIQUE': "https://stock.dsautomobiles.be/fr/stock",
    'ALLEMAGNE': "https://financing.dsautomobiles.store/bestand"
}

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
}

# =============================================================================
# FONCTIONS BACKEND
# =============================================================================

@st.cache_data(ttl=600) # Cache les résultats 10 min pour éviter de spammer
def fetch_content(url):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
            return response.read().decode('utf-8', errors='ignore')
    except Exception:
        return None

def run_scraper():
    results = []
    
    # Barre de progression
    total_steps = len(MODERN_SITES) + len(LEGACY_SITES)
    progress_bar = st.progress(0)
    status_text = st.empty()
    step = 0

    # 1. MODERN SITES
    for country, cfg in MODERN_SITES.items():
        status_text.text(f"Analyse en cours : {country}...")
        html = fetch_content(cfg['url'])
        
        if html:
            match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
            if match:
                data = json.loads(match.group(1))
                models = []
                def find_models(obj):
                    if isinstance(obj, dict):
                        if 'model' in obj and 'bodyStyle' in obj:
                            m, b = obj['model'], obj['bodyStyle']
                            if isinstance(m, dict) and isinstance(b, dict):
                                models.append({'id': m.get('id'), 'bodyId': b.get('id'), 'name': m.get('title')})
                        for v in obj.values(): find_models(v)
                    elif isinstance(obj, list):
                        for i in obj: find_models(i)
                find_models(data)
                
                # Unique models
                unique = {f"{m['id']}-{m['bodyId']}": m for m in models if m['name']}.values()

                for m in unique:
                    stock_url = f"{cfg['url']}/stock/{m['id']}/{m['bodyId']}?channel=b2c&latitude={cfg['lat']}&longitude={cfg['lon']}"
                    stock_html = fetch_content(stock_url)
                    if stock_html:
                        smatch = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', stock_html)
                        if smatch:
                            sdata = json.loads(smatch.group(1))
                            offers = sdata.get('props', {}).get('pageProps', {}).get('offers', {})
                            count = offers.get('count', 0) if isinstance(offers, dict) else len(offers) if isinstance(offers, list) else 0
                            
                            details = ""
                            if count > 0 and isinstance(offers, dict):
                                energies = offers.get('filters', {}).get('fuelTypes', [])
                                if energies:
                                    details = ", ".join([f"{e['title']} ({e['count']})" for e in energies])
                            
                            results.append({
                                'Pays': country, 'Modèle': m['name'], 'Stock': count, 'Type': 'Précis (API)', 'Détails': details
                            })
        
        step += 1
        progress_bar.progress(step / total_steps)

    # 2. LEGACY SITES
    for country, url in LEGACY_SITES.items():
        status_text.text(f"Analyse en cours : {country}...")
        html = fetch_content(url)
        
        if html:
            models = ["DS 3", "DS 4", "DS 7", "DS 9"]
            
            if country == 'ALLEMAGNE':
                for model in models:
                    # Correction: Utilisation de double quotes pour entourer la f-string
                    count = len(re.findall(rf"data-model-text=['\"]{model}['\"]", html, re.IGNORECASE))
                    if count > 0:
                        results.append({'Pays': country, 'Modèle': model, 'Stock': count, 'Type': 'Précis (HTML)', 'Détails': ''})
                        
            elif country == 'PORTUGAL':
                for model in models:
                    count = len(re.findall(rf'{model}.{{0,300}}(?:€|EUR|Preço)', html, re.IGNORECASE))
                    if count == 0 and "4" in model:
                         count = len(re.findall(rf'<h\d>[^<]*{model}[^<]*</h\d>', html, re.IGNORECASE))
                    if count > 0:
                        results.append({'Pays': country, 'Modèle': model, 'Stock': count, 'Type': 'Estimé', 'Détails': ''})
            
            else: # Generic
                # Try SEO JSON-LD first
                json_ld = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
                found_seo = False
                for j in json_ld:
                    try:
                        jd = json.loads(j)
                        if isinstance(jd, dict) and 'hasOfferCatalog' in jd:
                            count = len(jd['hasOfferCatalog'].get('itemListElement', []))
                            if count > 0:
                                results.append({'Pays': country, 'Modèle': 'Global', 'Stock': count, 'Type': 'Global (SEO)', 'Détails': ''})
                                found_seo = True
                    except: pass
                
                if not found_seo:
                    for model in models:
                        count = len(re.findall(rf'{model}.{{0,50}}(?:PureTech|BlueHDi|E-TENSE|Hybrid|Electric)', html, re.IGNORECASE))
                        if count > 0:
                            results.append({'Pays': country, 'Modèle': model, 'Stock': count, 'Type': 'Estimé (Text)', 'Détails': ''})

        step += 1
        progress_bar.progress(step / total_steps)
    
    status_text.text("Terminé !")
    time.sleep(1)
    status_text.empty()
    progress_bar.empty()
    
    return pd.DataFrame(results)

# =============================================================================
# INTERFACE UTILISATEUR
# =============================================================================

st.title("🇪🇺 DS Automobiles - European Stock Monitor")
st.markdown("Ce tableau de bord scanne les stocks de véhicules neufs disponibles en ligne dans 9 pays européens.")

if st.button("🔄 Lancer le Scan (Live)"):
    df = run_scraper()
    
    if not df.empty:
        # Métriques Clés
        total_stock = df['Stock'].sum()
        top_country = df.groupby('Pays')['Stock'].sum().idxmax()
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Stock Total Europe", total_stock)
        col2.metric("Top Pays", top_country)
        col3.metric("Nombre de Pays", df['Pays'].nunique())
        
        # Affichage Tableau
        st.dataframe(df, use_container_width=True)
        
        # Export Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Sheet1')
            
        st.download_button(
            label="📥 Télécharger le rapport Excel",
            data=output.getvalue(),
            file_name=f"DS_Stocks_Europe_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
            mime="application/vnd.ms-excel"
        )
    else:
        st.error("Aucune donnée trouvée. Vérifiez la connexion.")
