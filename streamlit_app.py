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
# CONFIGURATION V7 (STABLE & PRAGMATIQUE)
# =============================================================================

st.set_page_config(page_title="DS Stock Europe V7", page_icon="🇪🇺", layout="wide")

# 1. Pays avec API certifiée (Données sûres)
API_SITES = {
    'FRANCE':      {'url': "https://store.dsautomobiles.fr",    'lat': "46.2276", 'lon': "2.2137"},
    'ESPAGNE':     {'url': "https://store.dsautomobiles.es",    'lat': "40.4168", 'lon': "-3.7038"},
    'ITALIE':      {'url': "https://store.dsautomobiles.it",    'lat': "41.9028", 'lon': "12.4964"},
    # L'Allemagne fonctionne très bien en mode Legacy (attributs HTML)
}

# 2. Pays avec Lecture HTML ("1 sur 37")
TEXT_SITES = {
    'ROYAUME-UNI': "https://www.stellantisandyou.co.uk/ds/new-cars-in-stock",
    'POLOGNE':     "https://sklep.dsautomobiles.pl/",
    'PORTUGAL':    "https://dsonlinestore.dsautomobiles.pt/listagem", 
    'PAYS-BAS':    "https://voorraad.dsautomobiles.nl/stock",
    'BELGIQUE':    "https://stock.dsautomobiles.be/fr/stock",
    'ALLEMAGNE':   "https://financing.dsautomobiles.store/bestand"
}

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# =============================================================================
# MOTEURS
# =============================================================================

def fetch_content(url):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
            return response.read().decode('utf-8', errors='ignore')
    except: return None

def analyze_api_site(country, cfg):
    """Scan via API Next.js (Méthode la plus fiable)"""
    results = []
    html = fetch_content(cfg['url'])
    if not html: return results

    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
    if not match: return results
    
    data = json.loads(match.group(1))
    
    # 1. Lister les modèles
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
    
    unique_models = {f"{m['id']}-{m['bodyId']}": m for m in models if m['name']}.values()

    # 2. Interroger le stock
    for m in unique_models:
        stock_url = f"{cfg['url']}/stock/{m['id']}/{m['bodyId']}?channel=b2c&latitude={cfg['lat']}&longitude={cfg['lon']}"
        s_html = fetch_content(stock_url)
        if s_html:
            s_match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', s_html)
            if s_match:
                s_data = json.loads(s_match.group(1))
                offers = s_data.get('props', {}).get('pageProps', {}).get('offers', {})
                count = offers.get('count', 0) if isinstance(offers, dict) else len(offers) if isinstance(offers, list) else 0
                
                # Détails Énergie
                details = ""
                if count > 0 and isinstance(offers, dict):
                    energies = offers.get('filters', {}).get('fuelTypes', [])
                    if energies:
                        details = ", ".join([f"{e['title']} ({e['count']})" for e in energies])
                
                results.append({'Pays': country, 'Modèle': m['name'], 'Stock': count, 'Type': 'Certifié (API)', 'Détails': details})
    return results

def analyze_text_site(country, url):
    """Scan via Lecture HTML (Recherche '1 sur 37')"""
    results = []
    html = fetch_content(url)
    if not html: return results

    # Liste des modèles à chercher
    target_models = ["DS 3", "DS 4", "DS 7", "DS 9"]
    
    # 1. Cas Spécial : Allemagne (Attributs HTML précis)
    if country == 'ALLEMAGNE':
        for model in target_models:
            # Recherche stricte sur attribut data-model-text="DS 7"
            count = len(re.findall(rf"data-model-text=['"]{model}['"]", html, re.IGNORECASE))
            if count > 0:
                results.append({'Pays': country, 'Modèle': model, 'Stock': count, 'Type': 'HTML Tags', 'Détails': ''})
        return results

    # 2. Cas Général : Recherche de compteurs "sur X"
    # On cherche d'abord un compteur global
    global_count = 0
    patterns = [
        r'(?:sur|of|z|von|van|di|total)\s*(\d{1,4})', # "sur 37"
        r'(\d{1,4})\s*(?:results|r.sultats|voertuigen|Fahrzeuge|wynik.w)' # "37 résultats"
    ]
    for p in patterns:
        matches = re.findall(p, html, re.IGNORECASE)
        if matches:
            # On prend le max trouvé (souvent le total)
            candidates = [int(m) for m in matches if int(m) < 5000]
            if candidates:
                global_count = max(candidates)
                break
    
    if global_count > 0:
        # Si on a un total global, on essaie de le répartir ou on l'affiche tel quel
        results.append({'Pays': country, 'Modèle': 'TOTAL SITE', 'Stock': global_count, 'Type': 'Lecture Pagination', 'Détails': 'Total déduit du texte (ex: "1 sur X")'})
    
    else:
        # Fallback : Si pas de total global, on compte les occurrences de modèles
        for model in target_models:
            # On compte combien de fois le modèle est cité près d'un mot clé technique
            pattern = rf'{model}.{{0,50}}(?:PureTech|BlueHDi|E-TENSE|Hybrid|Electric|Performance)'
            count = len(re.findall(pattern, html, re.IGNORECASE))
            if count > 0:
                results.append({'Pays': country, 'Modèle': model, 'Stock': count, 'Type': 'Estimation', 'Détails': 'Mentions textuelles'})

    return results

# =============================================================================
# INTERFACE
# =============================================================================

st.title("🚗 DS Stock Europe V7 - Stable")

if st.button("🚀 LANCER LE SCAN"):
    all_data = []
    total_steps = len(API_SITES) + len(TEXT_SITES)
    bar = st.progress(0)
    
    # 1. API (Fiable)
    for i, (name, cfg) in enumerate(API_SITES.items()):
        st.write(f"✅ Scan API : {name}...")
        res = analyze_api_site(name, cfg)
        all_data.extend(res)
        bar.progress((i + 1) / total_steps)

    # 2. TEXTE (Lecture "1 sur X")
    for j, (name, url) in enumerate(TEXT_SITES.items()):
        st.write(f"🔎 Lecture Page : {name}...")
        res = analyze_text_site(name, url)
        if not res:
            res = [{'Pays': name, 'Modèle': 'Inconnu', 'Stock': 0, 'Type': 'Echec', 'Détails': 'Site muet'}]
        all_data.extend(res)
        bar.progress((len(API_SITES) + j + 1) / total_steps)

    # RÉSULTATS
    if all_data:
        df = pd.DataFrame(all_data)
        st.success("Analyse terminée.")
        st.dataframe(df, use_container_width=True)
        
        # EXPORT EXCEL
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # Vue d'ensemble
            summary = df.groupby('Pays')['Stock'].sum().reset_index()
            summary.to_excel(writer, sheet_name='RECAP', index=False)
            # Détails par pays
            for c in df['Pays'].unique():
                df[df['Pays'] == c].to_excel(writer, sheet_name=c[:31], index=False)
        
        st.download_button("📥 Télécharger Excel", output.getvalue(), "DS_Stock_Europe_V7.xlsx")

