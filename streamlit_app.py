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
# CONFIGURATION DES 10 MARCHÉS
# =============================================================================

st.set_page_config(page_title="DS Stock Europe V6", page_icon="🇪🇺", layout="wide")

# Liste des marchés (10 au total)
# Type API = Direct Stellantis / Type TEXT = Recherche "1 sur X"
MARKETS = {
    'FRANCE':      {'code': 'FR', 'type': 'API'},
    'GERMANY':     {'code': 'DE', 'type': 'API'},
    'ITALY':       {'code': 'IT', 'type': 'API'},
    'SPAIN':       {'code': 'ES', 'type': 'API'},
    'AUSTRIA':     {'code': 'AT', 'type': 'API'},
    'NETHERLANDS': {'code': 'NL', 'type': 'API'},
    'PORTUGAL':    {'code': 'PT', 'type': 'API'},
    'BELUX':       {'code': ['BE', 'LU'], 'type': 'API'}, # Fusion BE + LU
    'POLAND':      {'url': "https://sklep.dsautomobiles.pl/", 'type': 'TEXT'},
    'UK':          {'url': "https://www.stellantisandyou.co.uk/ds/new-cars-in-stock", 'type': 'TEXT'}
}

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# =============================================================================
# MOTEURS DE SCRAPING
# =============================================================================

def get_api_stock(market_codes):
    """Interroge le backend Stellantis pour un ou plusieurs codes pays."""
    if isinstance(market_codes, str): market_codes = [market_codes]
    
    combined_results = {}
    
    for code in market_codes:
        url = f"https://api.mpsa.com/dealer-stock-offers/v1/offers?brand=ds&market={code}&channel=b2c&item_per_page=1&facet=model"
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
                data = json.loads(response.read().decode('utf-8'))
                for facet in data.get('facets', []):
                    if facet.get('id') == 'model':
                        for bucket in facet.get('buckets', []):
                            model = bucket.get('label')
                            count = bucket.get('count', 0)
                            combined_results[model] = combined_results.get(model, 0) + count
        except: pass
    
    return combined_results

def get_text_stock(url):
    """Cherche le compteur de type '1 sur 37' dans le HTML."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            # Cherche "sur X", "of X", "z X", "von X"
            patterns = [
                r'(?:sur|of|z|von|van|di|total)\s*(\d{1,4})',
                r'(\d{1,4})\s*(?:results|r.sultats|voertuigen|Fahrzeuge|wynik.w)'
            ]
            for p in patterns:
                matches = re.findall(p, html, re.I)
                if matches:
                    return {"GLOBAL": max([int(m) for m in matches if int(m) < 5000])}
    except: pass
    return {}

# =============================================================================
# INTERFACE STREAMLIT
# =============================================================================

st.title("🚗 DS Europe Stock Monitor - Version 10 Pays (BELUX inclus)")

if st.button("🚀 LANCER L'ANALYSE CERTIFIÉE"):
    all_data = []
    bar = st.progress(0)
    
    for i, (name, cfg) in enumerate(MARKETS.items()):
        st.write(f"⏳ Analyse : {name}...")
        
        if cfg['type'] == 'API':
            stock_map = get_api_stock(cfg['code'])
        else:
            stock_map = get_text_stock(cfg['url'])
            
        if stock_map:
            for model, count in stock_map.items():
                all_data.append({'Pays': name, 'Modèle': model, 'Stock': count})
        else:
            all_data.append({'Pays': name, 'Modèle': 'Indisponible', 'Stock': 0})
            
        bar.progress((i + 1) / len(MARKETS))

    if all_data:
        df = pd.DataFrame(all_data)
        st.success("Analyse terminée.")
        
        # Affichage du tableau
        st.dataframe(df, use_container_width=True)
        
        # Export Excel Multi-onglets
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # Onglet Résumé
            summary = df.groupby('Pays')['Stock'].sum().reset_index()
            summary.to_excel(writer, sheet_name='RECAPITULATIF', index=False)
            
            # Un onglet par pays
            for country in df['Pays'].unique():
                df[df['Pays'] == country].to_excel(writer, sheet_name=country[:31], index=False)
        
        st.download_button("📥 Télécharger le Rapport Excel", output.getvalue(), "DS_Stock_Europe_10Pays.xlsx")
    else:
        st.error("Aucune donnée récupérée. Vérifiez votre connexion.")