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
# CONFIGURATION DES 10 PAYS
# =============================================================================

st.set_page_config(page_title="DS Stock Europe 10", page_icon="🇪🇺", layout="wide")

# On définit les 10 pays cibles avec leurs points GPS centraux
TARGET_COUNTRIES = {
    'FRANCE':      {'url': "https://store.dsautomobiles.fr",    'lat': "46.2276", 'lon': "2.2137",  'type': 'API'},
    'UK':          {'url': "https://store.dsautomobiles.co.uk", 'lat': "52.4862", 'lon': "-1.8904", 'type': 'API'},
    'GERMANY':     {'url': "https://store.dsautomobiles.de",    'lat': "51.1657", 'lon': "10.4515", 'type': 'API'},
    'ITALY':       {'url': "https://store.dsautomobiles.it",    'lat': "41.9028", 'lon': "12.4964", 'type': 'API'},
    'SPAIN':       {'url': "https://store.dsautomobiles.es",    'lat': "40.4168", 'lon': "-3.7038", 'type': 'API'},
    'BELGIUM':     {'url': "https://stock.dsautomobiles.be/fr", 'lat': "50.8503", 'lon': "4.3517",  'type': 'HTML'},
    'NETHERLANDS': {'url': "https://voorraad.dsautomobiles.nl", 'lat': "52.3676", 'lon': "4.9041",  'type': 'HTML'},
    'PORTUGAL':    {'url': "https://dsonlinestore.dsautomobiles.pt", 'lat': "38.7223", 'lon': "-9.1393", 'type': 'HTML'},
    'POLAND':      {'url': "https://sklep.dsautomobiles.pl",    'lat': "52.2297", 'lon': "21.0122", 'type': 'HTML'},
    'AUSTRIA':     {'url': "https://financing.dsautomobiles.at", 'lat': "48.2082", 'lon': "16.3738", 'type': 'HTML'}
}

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
}

# =============================================================================
# FONCTIONS DE SCRAPING
# =============================================================================

def fetch_json(url):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
            html = response.read().decode('utf-8', errors='ignore')
            match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
            if match: return json.loads(match.group(1))
    except: pass
    return None

def find_models_recursive(data):
    models = []
    def walk(obj):
        if isinstance(obj, dict):
            if 'model' in obj and 'bodyStyle' in obj:
                m, b = obj['model'], obj['bodyStyle']
                if isinstance(m, dict) and isinstance(b, dict):
                    mid, bid, name = m.get('id'), b.get('id'), m.get('title')
                    if mid and bid and name: models.append({'id': mid, 'bodyId': bid, 'name': name})
            for v in obj.values(): walk(v)
        elif isinstance(obj, list):
            for i in obj: walk(i)
    walk(data)
    return models

def run_global_scan():
    all_data = []
    progress = st.progress(0)
    status = st.empty()
    
    for idx, (name, cfg) in enumerate(TARGET_COUNTRIES.items()):
        status.text(f"🌍 Analyse en cours : {name}...")
        
        if cfg['type'] == 'API':
            # Moteur API (Plus précis)
            home = fetch_json(cfg['url'] + "/configurable") or fetch_json(cfg['url'])
            if home:
                models = find_models_recursive(home)
                unique = {f"{m['id']}-{m['bodyId']}": m for m in models}.values()
                for m in unique:
                    stock_url = f"{cfg['url']}/stock/{m['id']}/{m['bodyId']}?channel=b2c&latitude={cfg['lat']}&longitude={cfg['lon']}"
                    s_data = fetch_json(stock_url)
                    if s_data:
                        offers = s_data.get('props', {}).get('pageProps', {}).get('offers', {})
                        count = offers.get('count', 0) if isinstance(offers, dict) else 0
                        all_data.append({'Pays': name, 'Modèle': m['name'], 'Stock': count, 'Détails': 'API Live'})
        
        else:
            # Moteur HTML (Estimation pour les sites résistants)
            req = urllib.request.Request(cfg['url'], headers=HEADERS)
            try:
                with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                    html = resp.read().decode('utf-8', errors='ignore')
                    for model in ["DS 3", "DS 4", "DS 7", "DS 9"]:
                        # Recherche data-attributes ou titres
                        count = len(re.findall(rf"data-model-text=['"]{model}['"]", html, re.I))
                        if count == 0:
                            count = len(re.findall(rf'{model}.{{0,50}}(?:PureTech|BlueHDi|E-TENSE|kW|ch)', html, re.I))
                        
                        if count > 0:
                            all_data.append({'Pays': name, 'Modèle': model, 'Stock': count, 'Détails': 'HTML Scan'})
            except: pass

        progress.progress((idx + 1) / len(TARGET_COUNTRIES))
    
    status.empty()
    return pd.DataFrame(all_data)

# =============================================================================
# INTERFACE & EXPORT EXCEL
# =============================================================================

st.title("🚗 DS Europe - Stock Monitor (10 Pays)")

if st.button("🏁 Lancer le Scan Européen"):
    df = run_global_scan()
    
    if not df.empty:
        st.write("### Résultats du Scan")
        st.dataframe(df, use_container_width=True)
        
        # Génération Excel PRO
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # 1. Onglet Résumé Global
            summary = df.groupby('Pays')['Stock'].sum().reset_index()
            summary.to_excel(writer, sheet_name='RESUME GLOBAL', index=False)
            
            # 2. Un onglet par Pays
            for country in df['Pays'].unique():
                country_df = df[df['Pays'] == country]
                # Nettoyage nom onglet (31 chars max)
                sheet_name = str(country)[:31]
                country_df.to_excel(writer, sheet_name=sheet_name, index=False)
                
                # Mise en forme
                workbook  = writer.book
                worksheet = writer.sheets[sheet_name]
                header_format = workbook.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1})
                for col_num, value in enumerate(country_df.columns.values):
                    worksheet.write(0, col_num, value, header_format)
                    worksheet.set_column(col_num, col_num, 20)

        st.download_button(
            label="📥 Télécharger l'Excel (1 onglet par pays)",
            data=output.getvalue(),
            file_name=f"DS_Stock_Europe_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.error("Échec du scan. Vérifiez la connexion aux sites.")
