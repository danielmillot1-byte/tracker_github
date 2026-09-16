# --- Ce script a été réalisé par F6FTC avec l'aide de l'IA Gemini---
# --- on vérifie ce qu'on recoit et ce qui est affiché---
import streamlit as st
from streamlit_folium import st_folium
import folium
import pandas as pd
import requests
import re
from datetime import datetime, timezone
import math
import os
from io import StringIO

# --- HEADER POUR LES REQUÊTES WEB ---
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HamRadioApp"}

# --- GESTION DE L'AUTO-RAFRAÎCHISSEMENT ---
try:
    from streamlit_autorefresh import st_autorefresh
    MODULE_AUTOREFRESH_INSTALLE = True
except ImportError:
    MODULE_AUTOREFRESH_INSTALLE = False

st.set_page_config(page_title="POTA / SOTA / WWFF Tracker", layout="wide")

# --- FONCTIONS DE TEMPS RÉVISÉES ---
def parser_heure(chaine_heure):
    if not chaine_heure: return None
    ch = str(chaine_heure).strip()
    
    if re.match(r'^\d{2}:\d{2}(:\d{2})?$', ch):
        maintenant = datetime.now(timezone.utc)
        if len(ch) == 5: ch += ":00"
        try:
            h, m, s = map(int, ch.split(':'))
            return maintenant.replace(hour=h, minute=m, second=s, microsecond=0)
        except:
            pass
            
    try:
        ch_iso = ch.replace('Z', '+00:00')
        dt = datetime.fromisoformat(ch_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass
        
    try:
        dt_str = ch[:19]
        if len(dt_str) == 16: dt_str += ":00"
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=timezone.utc)
    except:
        return None

def calculer_age(dt_spot):
    if not dt_spot: return "N/A", 99999
    maintenant = datetime.now(timezone.utc)
    delta = maintenant - dt_spot
    minutes = int(delta.total_seconds() / 60)
    
    if minutes < 0: return "À l'instant", 0
    if minutes < 60: return f"{minutes} min", minutes
    
    heures = minutes // 60
    reste_min = minutes % 60
    return f"{heures}h{reste_min:02d}", minutes

# --- FONCTIONS UTILITAIRES ---
def calculer_distance(lat1, lon1, lat2, lon2):
    R = 6371.0 
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def obtenir_bande(freq_mhz):
    if freq_mhz == 0: return "N/A"
    if 1.8 <= freq_mhz < 2.0: return "160m"
    if 3.5 <= freq_mhz < 4.0: return "80m"
    if 5.3 <= freq_mhz < 5.4: return "60m"
    if 7.0 <= freq_mhz < 7.3: return "40m"
    if 10.1 <= freq_mhz < 10.2: return "30m"
    if 14.0 <= freq_mhz < 14.35: return "20m"
    if 18.068 <= freq_mhz < 18.168: return "17m"
    if 21.0 <= freq_mhz < 21.45: return "15m"
    if 24.89 <= freq_mhz < 24.99: return "12m"
    if 28.0 <= freq_mhz < 29.7: return "10m"
    if 50.0 <= freq_mhz < 54.0: return "6m"
    if 144.0 <= freq_mhz < 148.0: return "2m"
    if 430.0 <= freq_mhz < 440.0: return "70cm"
    return "Autres"

def maidenhead_vers_latlon(grid):
    if not grid or grid == "N/A": return None
    grid = grid.strip().upper()
    if not re.match(r'^[A-R]{2}[0-9]{2}([A-X]{2})?$', grid): return None
    lon = (ord(grid[0]) - ord('A')) * 20 - 180
    lat = (ord(grid[1]) - ord('A')) * 10 - 90
    lon += int(grid[2]) * 2
    lat += int(grid[3]) * 1
    if len(grid) >= 6:
        lon += (ord(grid[4]) - ord('A')) * (5/60.0) + (2.5/60.0)
        lat += (ord(grid[5]) - ord('A')) * (2.5/60.0) + (1.25/60.0)
    else:
        lon += 1.0 
        lat += 0.5
    return lat, lon

def latlon_vers_maidenhead(lat, lon):
    if pd.isna(lat) or pd.isna(lon): 
        return "N/A"
    lon = float(lon) + 180.0
    lat = float(lat) + 90.0
    lon_field, lat_field = int(lon / 20), int(lat / 10)
    lon_sq, lat_sq = int((lon % 20) / 2), int((lat % 10) / 1)
    lon_sub, lat_sub = int((lon % 2) * 12), int((lat % 1) * 24)
    loc = (chr(ord('A') + lon_field) + chr(ord('A') + lat_field) +
           str(lon_sq) + str(lat_sq) +
           chr(ord('A') + lon_sub) + chr(ord('A') + lat_sub))
    return loc

@st.cache_data
def charger_dictionnaire_parcs():
    try:
        url_csv = "https://pota.app/all_parks_ext.csv"
        rep = requests.get(url_csv, headers=HEADERS, timeout=10)
        if rep.status_code == 200:
            df = pd.read_csv(StringIO(rep.text), index_col="reference", low_memory=False)
            return df
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

@st.cache_data
def charger_dictionnaire_sommets():
    try:
        url_csv = "https://storage.sota.org.uk/summitslist.csv"
        rep = requests.get(url_csv, headers=HEADERS, timeout=10)
        if rep.status_code == 200:
            df = pd.read_csv(StringIO(rep.text), skiprows=1, usecols=['SummitCode', 'SummitName', 'Latitude', 'Longitude'], index_col="SummitCode", low_memory=False)
            if not df.empty:
                df.index = df.index.astype(str).str.strip().str.upper()
            return df
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

@st.cache_data
def charger_dictionnaire_wwff():
    try:
        url_csv = "https://wwff.co/wwff-data/wwff_directory.csv"
        rep = requests.get(url_csv, headers=HEADERS, timeout=10)
        if rep.status_code == 200:
            df = pd.read_csv(StringIO(rep.text), low_memory=False)
            df.columns = df.columns.str.lower()
            if 'reference' in df.columns and 'latitude' in df.columns and 'longitude' in df.columns:
                df = df.set_index('reference')
                df.index = df.index.astype(str).str.strip().str.upper()
                return df
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=60)
def recuperer_spots(_dico_parcs, _dico_sommets, _dico_wwff):
    spots = []
    
    # 1. Traitement POTA
    try:
        rep_pota = requests.get("https://api.pota.app/spot/activator", headers=HEADERS, timeout=5)
        if rep_pota.status_code == 200:
            for spot in rep_pota.json():
                try: freq_mhz = float(spot.get('frequency', 0)) / 1000
                except: freq_mhz = 0
                reference = spot.get('reference', 'N/A')
                locator = spot.get('grid6') or spot.get('grid4') or "N/A"
                heure_dt = parser_heure(spot.get('spotTime'))
                
                nom = spot.get('name', 'N/A')
                coords = None
                
                if reference in _dico_parcs.index:
                    parc_data = _dico_parcs.loc[reference]
                    if isinstance(parc_data, pd.DataFrame): parc_data = parc_data.iloc[0]
                    coords = (float(parc_data['latitude']), float(parc_data['longitude']))
                    if nom == 'N/A' and 'name' in parc_data:
                        nom = str(parc_data['name'])
                else:
                    coords = maidenhead_vers_latlon(locator)
                
                spots.append({
                    'type': 'POTA', 'activateur': spot.get('activator', 'N/A'),
                    'reference': reference, 'nom': nom, 'freq_mhz': freq_mhz,
                    'bande': obtenir_bande(freq_mhz), 'mode': spot.get('mode', 'N/A'),
                    'locator': locator, 'coords': coords, 'heure_dt': heure_dt
                })
    except: pass

    # 2. Traitement SOTA
    try:
        rep_sota = requests.get("https://api2.sota.org.uk/api/spots/50", headers=HEADERS, timeout=5)
        if rep_sota.status_code == 200:
            for spot_brut in rep_sota.json():
                spot = {str(k).lower(): v for k, v in spot_brut.items()}
                
                try:
                    freq_val = spot.get('frequency') or spot.get('freq') or spot.get('qrg') or 0
                    freq_str = str(freq_val).replace(',', '.')
                    match = re.search(r"[-+]?\d*\.\d+|\d+", freq_str)
                    freq_mhz = float(match.group()) if match else 0
                    if freq_mhz > 1000: freq_mhz = freq_mhz / 1000
                except: 
                    freq_mhz = 0
                
                chaine_temps = spot.get('timestamp') or spot.get('time') or spot.get('spottime')
                heure_dt = parser_heure(chaine_temps)
                
                summit = spot.get('summitcode') or spot.get('reference') or spot.get('summit') or 'N/A'
                reference = str(summit).strip().upper()
                reference = reference.replace('_', '-')
                reference = re.sub(r'-(\d{1,2})$', lambda m: f"-{m.group(1).zfill(3)}", reference)
                
                if reference != 'N/A' and reference not in _dico_sommets.index:
                    correspondances = [idx for idx in _dico_sommets.index if str(idx).endswith(f"/{reference}")]
                    if correspondances: reference = correspondances[0]  
                
                nom = 'N/A'
                coords = None
                locator_calcule = "N/A"
                if reference in _dico_sommets.index:
                    sommet_data = _dico_sommets.loc[reference]
                    if isinstance(sommet_data, pd.DataFrame): sommet_data = sommet_data.iloc[0]
                    coords = (float(sommet_data['Latitude']), float(sommet_data['Longitude']))
                    locator_calcule = latlon_vers_maidenhead(coords[0], coords[1])
                    if 'SummitName' in sommet_data:
                        nom = str(sommet_data['SummitName'])
                
                activateur = spot.get('activatorcallsign') or spot.get('activator') or spot.get('callsign') or 'N/A'
                mode = spot.get('mode') or 'N/A'
                
                spots.append({
                    'type': 'SOTA', 'activateur': str(activateur).strip().upper(),
                    'reference': reference, 'nom': nom, 'freq_mhz': freq_mhz,
                    'bande': obtenir_bande(freq_mhz), 'mode': str(mode).strip().upper(),
                    'locator': locator_calcule, 'coords': coords, 'heure_dt': heure_dt
                })
    except Exception as e:
        st.error(f"Erreur API SOTA: {e}")
    
    # 3. Traitement WWFF
    try:
        rep_wwff = requests.get("https://spots.wwff.co/static/spots.json", headers=HEADERS, timeout=5)
        if rep_wwff.status_code == 200:
            spots_wwff = rep_wwff.json()

            for spot in spots_wwff:
                try: 
                    freq_khz = spot.get('frequency_khz') or spot.get('frequency') or spot.get('qrg') or 0
                    freq_mhz = float(freq_khz) / 1000 if float(freq_khz) > 1000 else float(freq_khz)
                except: 
                    freq_mhz = 0.0
                
                reference = str(spot.get('reference', 'N/A')).strip().upper()
                activateur = str(spot.get('activator', 'N/A')).strip().upper()
                mode = str(spot.get('mode', 'N/A')).strip().upper()
                nom = str(spot.get('name', 'N/A'))
                
                chaine_temps = spot.get('spot_time_formatted') or spot.get('time') or spot.get('timestamp')
                heure_dt = parser_heure(chaine_temps)
                
                coords = None
                locator_calcule = "N/A"
                try:
                    lat = spot.get('latitude')
                    lon = spot.get('longitude')
                    if lat is not None and lon is not None:
                        coords = (float(lat), float(lon))
                        locator_calcule = latlon_vers_maidenhead(float(lat), float(lon))
                except:
                    pass
                
                if coords is None and reference in _dico_wwff.index:
                    wwff_data = _dico_wwff.loc[reference]
                    if isinstance(wwff_data, pd.DataFrame): wwff_data = wwff_data.iloc[0]
                    if nom == 'N/A' and 'name' in wwff_data:
                        nom = str(wwff_data['name'])
                    try:
                        lat_csv = float(wwff_data['latitude'])
                        lon_csv = float(wwff_data['longitude'])
                        if not pd.isna(lat_csv) and not pd.isna(lon_csv):
                            coords = (lat_csv, lon_csv)
                            locator_calcule = latlon_vers_maidenhead(lat_csv, lon_csv)
                    except:
                        pass
                
                spots.append({
                    'type': 'WWFF', 'activateur': activateur,
                    'reference': reference, 'nom': nom, 'freq_mhz': freq_mhz,
                    'bande': obtenir_bande(freq_mhz), 'mode': mode,
                    'locator': locator_calcule, 'coords': coords, 'heure_dt': heure_dt
                })
    except: pass

    return spots

def injecter_bandeau_js(carte, coords_utilisateur):
    map_name = carte.get_name()
    qth_lat = coords_utilisateur[0] if coords_utilisateur else 0.0
    qth_lon = coords_utilisateur[1] if coords_utilisateur else 0.0
    has_qth = "true" if coords_utilisateur else "false"
    
    js_code = f"""
    <script>
    setTimeout(function() {{
        var myMap = window['{map_name}'];
        if (!myMap) {{
            var keys = Object.keys(window).filter(k => k.startsWith('map_'));
            if (keys.length > 0) myMap = window[keys[0]];
        }}
        
        if (myMap) {{
            var qthLat = {qth_lat};
            var qthLon = {qth_lon};
            var hasQth = {has_qth};
            
            var infoControl = L.control({{position: 'topright'}});
            infoControl.onAdd = function (map) {{
                var div = L.DomUtil.create('div', 'info');
                div.innerHTML = '<b>Infos Curseur</b><br>Distance: -<br>Azimut: -<br>Locator: -';
                div.style.backgroundColor = 'rgba(255, 255, 255, 0.9)';
                div.style.padding = '8px 12px';
                div.style.border = '2px solid #777';
                div.style.borderRadius = '5px';
                div.style.fontFamily = 'Arial, sans-serif';
                div.style.fontSize = '14px';
                div.style.lineHeight = '1.4';
                div.style.boxShadow = '0 0 10px rgba(0,0,0,0.2)';
                return div;
            }};
            
            infoControl.addTo(myMap);

            myMap.on('mousemove', function(e) {{
                var lat = e.latlng.lat;
                var lng = e.latlng.lng;
                var lon_m = lng + 180;
                var lat_m = lat + 90;
                var upper = "ABCDEFGHIJKLMNOPQRSTUVWX";
                var lower = "abcdefghijklmnopqrstuvwx";
                var num = "0123456789";
                
                var idx1 = Math.max(0, Math.min(17, Math.floor(lon_m / 20)));
                var idx2 = Math.max(0, Math.min(17, Math.floor(lat_m / 10)));
                var idx3 = Math.max(0, Math.min(9, Math.floor((lon_m % 20) / 2)));
                var idx4 = Math.max(0, Math.min(9, Math.floor((lat_m % 10) / 1)));
                var idx5 = Math.max(0, Math.min(23, Math.floor((lon_m % 2) * 12)));
                var idx6 = Math.max(0, Math.min(23, Math.floor((lat_m % 1) * 24)));
                
                var loc = upper[idx1] + upper[idx2] + num[idx3] + num[idx4] + lower[idx5] + lower[idx6];
                
                if (hasQth) {{
                    var R = 6371; 
                    var dLat = (lat - qthLat) * Math.PI / 180;
                    var dLon = (lng - qthLon) * Math.PI / 180;
                    var a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                            Math.cos(qthLat * Math.PI / 180) * Math.cos(lat * Math.PI / 180) *
                            Math.sin(dLon/2) * Math.sin(dLon/2);
                    var c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
                    var dist = (R * c).toFixed(0);
                    
                    var l1 = qthLat * Math.PI / 180;
                    var l2 = lat * Math.PI / 180;
                    var dl = (lng - qthLon) * Math.PI / 180;
                    var y = Math.sin(dl) * Math.cos(l2);
                    var x = Math.cos(l1) * Math.sin(l2) - Math.sin(l1) * Math.cos(l2) * Math.cos(dl);
                    var az = ((Math.atan2(y, x) * 180 / Math.PI) + 360) % 360;
                    az = az.toFixed(0);
                    
                    document.querySelector('.info').innerHTML = '<b>Infos Curseur</b><br>Distance: ' + dist + ' km<br>Azimut: ' + az + ' °<br>Locator: <span style="color:blue; font-weight:bold;">' + loc + '</span>';
                }} else {{
                    document.querySelector('.info').innerHTML = '<b>Infos Curseur</b><br>Distance: N/A<br>Azimut: N/A<br>Locator: <span style="color:blue; font-weight:bold;">' + loc + '</span>';
                }}
            }});
        }}
    }}, 1000);
    </script>
    """
    carte.get_root().html.add_child(folium.Element(js_code))

# --- INITIALISATION SESSION STATE ---
if 'call_input' not in st.session_state:
    st.session_state.call_input = ""
if 'loc_input' not in st.session_state:
    st.session_state.loc_input = ""
if 'alertes_acquittees' not in st.session_state:
    st.session_state.alertes_acquittees = set()

def gerer_acquittements():
    if "editeur_alertes" in st.session_state:
        modifs = st.session_state.editeur_alertes.get("edited_rows", {})
        for index_label, changements in modifs.items():
            if changements.get("Acquitter") == True:
                st.session_state.alertes_acquittees.add(str(index_label))

# --- BARRE LATÉRALE (SIDEBAR) ---
st.sidebar.title("📻 Contrôles")

if MODULE_AUTOREFRESH_INSTALLE:
    auto_refresh = st.sidebar.checkbox("Activer l'auto-rafraîchissement (2 min)", value=False)
    if auto_refresh:
        st_autorefresh(interval=120000, limit=None, key="autorefresh_spots")

st.sidebar.subheader("Vos Coordonnées")
indicatif = st.sidebar.text_input("Mon indicatif", key="call_input")
locator_utilisateur = st.sidebar.text_input("Mon locator", key="loc_input")

st.sidebar.subheader("Filtres d'affichage")
afficher_pota = st.sidebar.checkbox("Afficher les POTA", value=True)
afficher_sota = st.sidebar.checkbox("Afficher les SOTA", value=True)
afficher_wwff = st.sidebar.checkbox("Afficher les WWFF (Fauna Flora)", value=True)

# --- NOUVEAUX MENUS DÉROULANTS (AVEC MULTISELECT) ---
liste_bandes = ["160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m", "4m", "2m", "70cm", "Autres"]
bandes_choisies = st.sidebar.multiselect("Filtrer par Bandes", liste_bandes, default=liste_bandes) 

liste_modes = ["Tous", "CW", "SSB", "FT8", "FM", "Autres"]
mode_choisi = st.sidebar.selectbox("Filtrer par Mode", liste_modes, index=0)
# ---------------------------------

age_max = st.sidebar.slider("Âge maximum des spots (minutes)", min_value=10, max_value=240, value=45, step=5)

st.sidebar.subheader("Logs (Déjà contactés)")
fichier_log_pota = st.sidebar.file_uploader("Importer Log POTA", type=["adi", "csv", "txt"], key="pota")
fichier_log_sota = st.sidebar.file_uploader("Importer Log SOTA", type=["adi", "csv", "txt"], key="sota")
fichier_log_wwff = st.sidebar.file_uploader("Importer Log WWFF", type=["adi", "csv", "txt"], key="wwff")

refs_contactees_pota = set()
if fichier_log_pota:
    contenu_pota = fichier_log_pota.read().decode("utf-8", errors="ignore").upper()
    refs_contactees_pota.update(re.findall(r'[A-Z0-9]{1,4}[/-][A-Z0-9]{2,5}', contenu_pota))
    st.sidebar.success(f"{len(refs_contactees_pota)} Réf POTA trouvées.")

refs_contactees_sota = set()
if fichier_log_sota:
    contenu_sota = fichier_log_sota.read().decode("utf-8", errors="ignore").upper()
    refs_contactees_sota.update(re.findall(r'[A-Z0-9]{1,4}[/-][A-Z0-9]{2,5}', contenu_sota))
    st.sidebar.success(f"{len(refs_contactees_sota)} Réf SOTA trouvées.")

refs_contactees_wwff = set()
if fichier_log_wwff:
    contenu_wwff = fichier_log_wwff.read().decode("utf-8", errors="ignore").upper()
    refs_contactees_wwff.update(re.findall(r'[A-Z0-9]{1,4}FF-[0-9]{4}', contenu_wwff))
    st.sidebar.success(f"{len(refs_contactees_wwff)} Réf WWFF trouvées.")

st.sidebar.subheader("🔕 Gestion des Alertes")
btn_tout_ack = st.sidebar.button("Tout acquitter (Masquer)", use_container_width=True)
btn_annuler_ack = st.sidebar.button("Annuler les acquittements", use_container_width=True)

# --- INTERFACE PRINCIPALE ---
titre_app = f"🌍 POTA, SOTA, WWFF Tracker - {indicatif}" if indicatif else "🌍 POTA, SOTA, WWFF Tracker"
st.title(titre_app)

col_date, col_btn = st.columns([4, 1])
maintenant_local = datetime.now().strftime("%d/%m/%Y %H:%M LOC")
with col_date:
    st.info(f"🕒 **Actualisé à :** {maintenant_local}")
with col_btn:
    if st.button("🔄 Rafraîchir manuellement", use_container_width=True):
        recuperer_spots.clear()

with st.spinner('Récupération des données en cours...'):
    dico_parcs = charger_dictionnaire_parcs()
    dico_sommets = charger_dictionnaire_sommets()
    dico_wwff = charger_dictionnaire_wwff()
    spots_bruts = recuperer_spots(dico_parcs, dico_sommets, dico_wwff)

# Dédoublonnage
spots_uniques = {}
for spot in spots_bruts:
    cle = f"{spot['activateur']}_{spot['reference']}_{spot['bande']}"
    if cle not in spots_uniques:
        spots_uniques[cle] = spot
    else:
        dt_existant = spots_uniques[cle]['heure_dt']
        dt_nouveau = spot['heure_dt']
        if dt_nouveau and dt_existant:
            if dt_nouveau > dt_existant:
                spots_uniques[cle] = spot
        elif dt_nouveau:
            spots_uniques[cle] = spot
            
spots_bruts = list(spots_uniques.values())

if btn_annuler_ack:
    st.session_state.alertes_acquittees.clear()
    st.rerun()

if btn_tout_ack:
    for s in spots_bruts:
        cle = f"{s['activateur']}_{s['reference']}_{s['bande']}"
        st.session_state.alertes_acquittees.add(cle)
    st.rerun()

coords_utilisateur = maidenhead_vers_latlon(locator_utilisateur) if locator_utilisateur else None

spots_filtres = []
for spot in spots_bruts:
    if spot['type'] == 'POTA' and not afficher_pota: continue
    if spot['type'] == 'SOTA' and not afficher_sota: continue
    if spot['type'] == 'WWFF' and not afficher_wwff: continue
    
    # --- FILTRES BANDE ET MODE ---
    if spot['bande'] not in bandes_choisies:
        continue
        
    if mode_choisi != "Tous":
        mode_spot = str(spot['mode']).upper()
        if mode_choisi == "SSB" and mode_spot in ["USB", "LSB", "SSB"]:
            pass
        elif mode_choisi == "Autres":
            # On ignore les modes standards pour ne garder que les autres (FT4, MSK144, RTTY, etc.)
            if mode_spot in ["CW", "SSB", "USB", "LSB", "FT8", "FM"]:
                continue
        elif mode_choisi not in mode_spot:
            continue
    # -----------------------------
    
    _, minutes_age = calculer_age(spot['heure_dt'])
    if minutes_age > age_max:
        continue
    
    cle_alerte = f"{spot['activateur']}_{spot['reference']}_{spot['bande']}"
    if cle_alerte in st.session_state.alertes_acquittees:
        continue
    
    spot['distance'] = None
    if coords_utilisateur and spot['coords']:
        spot['distance'] = calculer_distance(coords_utilisateur[0], coords_utilisateur[1], spot['coords'][0], spot['coords'][1])
    
    spot['deja_contacte_pota'] = spot['type'] == 'POTA' and spot['reference'].upper() in refs_contactees_pota
    spot['deja_contacte_sota'] = spot['type'] == 'SOTA' and spot['reference'].upper() in refs_contactees_sota
    spot['deja_contacte_wwff'] = spot['type'] == 'WWFF' and spot['reference'].upper() in refs_contactees_wwff
    
    spot['deja_contacte'] = spot['deja_contacte_pota'] or spot['deja_contacte_sota'] or spot['deja_contacte_wwff']
    
    spots_filtres.append(spot)

# --- GÉNÉRATION DE LA CARTE ---
centre_carte = coords_utilisateur if coords_utilisateur else [46.5, 2.0]
carte = folium.Map(location=centre_carte, zoom_start=5, tiles="OpenStreetMap")

# --- INJECTION CSS POUR ANIMATION ET FONT-AWESOME (Vraies épingles) ---
css_animation = """
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css"/>
<style>
@keyframes pulse {
    0% { transform: scale(0.5); opacity: 0.8; }
    100% { transform: scale(3.5); opacity: 0; }
}
</style>
"""
carte.get_root().html.add_child(folium.Element(css_animation))

# --- LÉGENDE MISE À JOUR (Épingles pour Nouveau / Points pour QSO) ---
legende_html = '''
<div style="position: absolute; 
     bottom: 30px; left: 30px; width: max-content; min-width: 200px; height: auto; 
     border:2px solid grey; z-index:9999; font-size:14px;
     background-color:white; padding: 10px; border-radius: 5px; box-shadow: 0 0 10px rgba(0,0,0,0.2);">
     <b>📍 Légende</b><br>
     <span style="color: green;">📍 Vert</span> (Nouv) / <span style="color: #007bff;">🔵 Bleu</span> (QSO) : POTA<br>
     <span style="color: orange;">📍 Orange</span> (Nouv) / <span style="color: red;">🔴 Rouge</span> (QSO) : SOTA<br>
     <span style="color: purple;">📍 Violet</span> (Nouv) / <span style="color: #4b0082;">🟣 Violet foncé</span> (QSO) : WWFF<br>
     <div style="margin-top: 5px; display: flex; align-items: center;">
         <div style="width: 12px; height: 12px; border-radius: 50%; background-color: #28a745; animation: pulse 1.5s infinite; margin-right: 6px; flex-shrink: 0;"></div>
         <span>Spot clignotant : Nouveau</span>
     </div>
</div>
'''
carte.get_root().html.add_child(folium.Element(legende_html))

injecter_bandeau_js(carte, coords_utilisateur)

if coords_utilisateur and indicatif:
    folium.Marker(
        location=coords_utilisateur,
        popup=f"<b>Station : {indicatif}</b><br>Locator : {locator_utilisateur}",
        icon=folium.Icon(color="red", icon="home")
    ).add_to(carte)

spots_mappes = 0
for spot in spots_filtres:
    if spot['coords']:
        lat, lon = spot['coords']
        
        age_str, min_brut = calculer_age(spot['heure_dt'])
        heure_utc_str = spot['heure_dt'].strftime("%H:%M UTC") if spot['heure_dt'] else "N/A"
        dist_str = f"{spot['distance']:.0f} km" if spot['distance'] else "N/A"
        coords_str = f"{lat:.4f}, {lon:.4f}"
        
        if spot['deja_contacte']:
            # --- POPUP SIMPLIFIÉ POUR LES "DÉJÀ CONTACTÉS" EN PETITS POINTS ---
            html_popup_contacte = f"""
            <b>{spot['reference']}</b><br>
            <i>{spot.get('nom', 'N/A')}</i><br>
            ✅ <b>Déjà contacté</b>
            """
            
            if spot['type'] == "POTA": couleur_point = "#007bff"
            elif spot['type'] == "SOTA": couleur_point = "red"
            else: couleur_point = "#4b0082" 
            
            folium.CircleMarker(
                location=[lat, lon],
                radius=4, 
                color=couleur_point,
                fill=True,
                fill_color=couleur_point,
                fill_opacity=1.0,
                weight=1,
                popup=folium.Popup(html_popup_contacte, max_width=250),
                tooltip=f"{spot['reference']} - Déjà QSO"
            ).add_to(carte)
            
        else:
            # --- POPUP COMPLET POUR LES NOUVEAUX SPOTS EN VRAIES ÉPINGLES ---
            html_popup_nouveau = f"""
            <b>{spot['reference']} ({spot['type']})</b><br>
            <i>{spot.get('nom', 'N/A')}</i><br>
            ✨ <b>NOUVEAU</b><br>
            Activateur : <b>{spot['activateur']}</b><br>
            Fréq: {spot['freq_mhz']:.3f} MHz ({spot['bande']})<br>
            Mode: {spot['mode']}<br>
            <hr style="margin:5px 0px;">
            Heure: <b>{heure_utc_str}</b><br>
            Âge: <span style="color: red;"><b>{age_str}</b></span><br>
            Grid: {spot['locator']}<br>
            Coords : <b>{coords_str}</b><br>
            Distance: {dist_str}
            """
            
            if spot['type'] == "POTA": couleur_epingle = "#28a745" # Vert
            elif spot['type'] == "SOTA": couleur_epingle = "#fd7e14" # Orange
            else: couleur_epingle = "#800080" # Violet
            
            html_epingle = f"""
            <div style="font-size: 26px; color: {couleur_epingle}; text-shadow: 1px 1px 2px rgba(0,0,0,0.8); text-align: center;">
                <i class="fa-solid fa-map-pin"></i>
            </div>
            """
            
            folium.Marker(
                location=[lat, lon],
                popup=folium.Popup(html_popup_nouveau, max_width=250),
                tooltip=f"{spot['activateur']} ({age_str})",
                icon=folium.DivIcon(html=html_epingle, icon_size=(26, 26), icon_anchor=(13, 26))
            ).add_to(carte)
        
            if spot['type'] == "POTA": couleur_flash = "#28a745"
            elif spot['type'] == "SOTA": couleur_flash = "#fd7e14"
            else: couleur_flash = "#800080"
            
            cercle_html = f"""
            <div style="
                width: 20px; 
                height: 20px; 
                background-color: {couleur_flash}; 
                border-radius: 50%; 
                animation: pulse 1.5s infinite;
                position: relative;
                left: -10px;
                top: -5px;
                pointer-events: none;
            "></div>
            """
            folium.Marker(
                location=[lat, lon],
                icon=folium.DivIcon(html=cercle_html, icon_size=(0, 0)) 
            ).add_to(carte)

        spots_mappes += 1

st.markdown(f"**{len(spots_filtres)} spots actifs** dont **{spots_mappes} géolocalisés** sur la carte. *(Les spots sans coordonnées s'affichent uniquement dans le tableau)*.")

cle_carte = f"carte_maj_{len(spots_filtres)}_{len(st.session_state.alertes_acquittees)}"

try:
    st_folium(carte, use_container_width=True, height=600, returned_objects=[], key=cle_carte)
except TypeError:
    st_folium(carte, width=1200, height=600, returned_objects=[], key=cle_carte)

# --- MODE DÉBOGAGE POUR COMPARER LES FLUX ---
st.markdown("---")
if st.checkbox("🔍 Mode Débogage : Comparer les données reçues et affichées"):
    col_debug1, col_debug2 = st.columns(2)
    with col_debug1:
        st.markdown(f"**Données brutes reçues : {len(spots_bruts)}**")
        st.dataframe(spots_bruts)
    with col_debug2:
        st.markdown(f"**Données affichées (filtrées) : {len(spots_filtres)}**")
        st.dataframe(spots_filtres)
st.markdown("---")

# --- TABLEAU DE BORD INTERACTIF ---
st.subheader("📋 Liste détaillée (Cochez 'Ack' pour masquer une alerte)")
donnees_tableau = []
for s in spots_filtres:
    dist_val = f"{s['distance']:.0f} km" if s['distance'] else ""
    age_str, minutes_age = calculer_age(s['heure_dt'])
    heure_utc = s['heure_dt'].strftime("%H:%M") if s['heure_dt'] else ""
    coords_val = f"{s['coords'][0]:.4f}, {s['coords'][1]:.4f}" if s['coords'] else ""
    
    cle_unique = f"{s['activateur']}_{s['reference']}_{s['bande']}"
    
    donnees_tableau.append({
        "ID_Unique": cle_unique,
        "Acquitter": False,
        "Déjà Qso": "✅" if s['deja_contacte'] else "✨",
        "Âge": age_str,
        "Heure (UTC)": heure_utc,
        "Prog": s['type'],
        "Act.": s['activateur'],
        "Réf": s['reference'],
        "Nom": s.get('nom', 'N/A'),
        "Fréq (MHz)": round(s['freq_mhz'], 3),
        "Bande": s['bande'],
        "Mode": s['mode'],
        "Dist.": dist_val,
        "Locator": s['locator'],
        "Lat/Lon": coords_val,
        "Minutes_Tri": minutes_age 
    })

if donnees_tableau:
    df_tableau = pd.DataFrame(donnees_tableau)
    df_tableau = df_tableau.set_index("ID_Unique")
    df_tableau = df_tableau.sort_values(by='Minutes_Tri').drop(columns=['Minutes_Tri'])
    
    edited_df = st.data_editor(
        df_tableau,
        column_config={
            "Acquitter": st.column_config.CheckboxColumn(
                "🔕 Ack",
                help="Cocher pour masquer définitivement cette alerte",
                default=False,
            )
        },
        disabled=["Déjà Qso", "Âge", "Heure (UTC)", "Prog", "Act.", "Réf", "Nom", "Fréq (MHz)", "Bande", "Mode", "Dist.", "Locator", "Lat/Lon"],
        hide_index=True,
        use_container_width=True,
        key="editeur_alertes",
        on_change=gerer_acquittements
    )
else:
    st.info("Aucun spot à afficher.")
