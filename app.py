import streamlit as st
import pandas as pd
import numpy as np
from sklearn.neighbors import NearestNeighbors
import requests
from bs4 import BeautifulSoup
import os
import json
import warnings
warnings.filterwarnings('ignore')

# --- BÜRO VE SÜTUN TESPİT HARİTASI ---
BURO_MAP = {
    "Bet365": {
        "MS 1": ["B365H", "B365_H", "Bet365_1"],
        "MS X": ["B365D", "B365_D", "Bet365_X"],
        "MS 2": ["B365A", "B365_A", "Bet365_2"],
        "2.5 Üst": ["B365>2.5", "B365_O25", "B365_Over25"],
        "2.5 Alt": ["B365<2.5", "B365_U25", "B365_Under25"],
        "1.5 Üst": ["B365>1.5", "B365_O15"],
        "KG Var": ["B365_BTS_Y", "B365_BTTS_Yes", "B365_KG_Var", "B365_KG"],
        "İY 1": ["B365_1H_1", "B365HTH", "HT_B365H", "B365_HT1"]
    },
    "Pinnacle": {
        "MS 1": ["PSH", "PinnacleH", "PS_H", "MaxH"],
        "MS X": ["PSD", "PinnacleD", "PS_D", "MaxD"],
        "MS 2": ["PSA", "PinnacleA", "PS_A", "MaxA"],
        "2.5 Üst": ["P>2.5", "PS>2.5", "Pinnacle>2.5", "Max>2.5"],
        "2.5 Alt": ["P<2.5", "PS<2.5", "Pinnacle<2.5", "Max<2.5"],
        "1.5 Üst": ["P>1.5", "PS>1.5", "Max>1.5"],
        "KG Var": ["PS_BTS_Y", "PS_BTTS_Yes", "Pinnacle_KG_Var", "PS_KG"],
        "İY 1": ["PS_1H_1", "PSHTH", "HT_PSH", "PS_HT1"]
    }
}

def sutun_getir(df, olasi_sutunlar):
    for col in olasi_sutunlar:
        if col in df.columns:
            return col
    return None

# --- SAYFA VE TEMA AYARLARI ---
st.set_page_config(page_title="MacApp Pro | Trading Terminal", page_icon="⚽", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0e1117; color: #fafafa; }
    .stMetric { background-color: #161b22; padding: 15px; border-radius: 10px; border: 1px solid #30363d; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { background-color: #21262d; border-radius: 6px; color: #c9d1d9; padding: 10px 20px; font-weight: 600; }
    .stTabs [aria-selected="true"] { background-color: #238636 !important; color: white !important; }
    </style>
""", unsafe_allow_html=True)

# --- GOOGLE SHEETS BAĞLANTISI ---
@st.cache_resource
def google_sheets_baglan():
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        key_dict = json.loads(st.secrets["GOOGLE_JSON"])
        creds = Credentials.from_service_account_info(
            key_dict, 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        )
        client = gspread.authorize(creds)
        sheet = client.open_by_url(st.secrets["GOOGLE_SHEET_URL"]).sheet1
        return sheet
    except Exception as e:
        return None

def takip_dosyasi_yukle():
    sheet = google_sheets_baglan()
    beklenen_sutunlar = [
        'ID', 'Tarih', 'Mac', 'Banko_Tahmin', 'Banko_Oran', 
        'Ideal_Tahmin', 'Ideal_Oran', 'IYMS_Tahmin', 'IYMS_Oran', 
        'Surpriz_Tahmin', 'Surpriz_Oran', 'IY_Skor', 'MS_Skor', 
        'Korner', 'Sut', 'Kart', 'Durum'
    ]
    if sheet is not None:
        try:
            veriler = sheet.get_all_records()
            if not veriler:
                sheet.append_row(beklenen_sutunlar)
                return pd.DataFrame(columns=beklenen_sutunlar)
            df = pd.DataFrame(veriler)
            for col in beklenen_sutunlar:
                if col not in df.columns: df[col] = "-"
            return df
        except:
            pass
    if os.path.exists("tahmin_gecmisi.csv"):
        return pd.read_csv("tahmin_gecmisi.csv")
    return pd.DataFrame(columns=beklenen_sutunlar)

def takip_dosyasi_kaydet(df_takip):
    sheet = google_sheets_baglan()
    if sheet is not None:
        try:
            sheet.clear()
            data = [df_takip.columns.values.tolist()] + df_takip.fillna("").values.tolist()
            sheet.update(range_name='A1', values=data)
            return
        except:
            pass
    df_takip.to_csv("tahmin_gecmisi.csv", index=False)

def oran_duzelt(deger):
    try:
        val = float(deger)
        if val > 10: return round(val / 100.0, 2)
        return round(val, 2)
    except: return deger

# --- YAPAY ZEKA VE KNN MOTORU ---
@st.cache_resource
def motoru_baslat():
    veri_yolu = "iddaa_arsiv_YEDEK.parquet" 
    df = pd.read_parquet(veri_yolu)
    
    df['Mac'] = df['HomeTeam'] + " - " + df['AwayTeam']
    df['res'] = df['FTR']  
    df['tot'] = df['FTHG'] + df['FTAG']  
    
    df['HT_Total'] = df['HTHG'] + df['HTAG']
    df['SH_Home'] = df['FTHG'] - df['HTHG']
    df['SH_Away'] = df['FTAG'] - df['HTAG']
    df['SH_Total'] = df['SH_Home'] + df['SH_Away']
    
    # 1. AKILLI ORAN KURTARICI: Sütunlar eksikse alternatif büroları devreye sok
    def sutun_sec(liste):
        for col in liste:
            if col in df.columns: return df[col]
        return pd.Series([np.nan]*len(df))

    df['Open_H'] = sutun_sec(['B365H', 'PSH', 'MaxH', 'AvgH'])
    df['Open_D'] = sutun_sec(['B365D', 'PSD', 'MaxD', 'AvgD'])
    df['Open_A'] = sutun_sec(['B365A', 'PSA', 'MaxA', 'AvgA'])
    df['Open_O25'] = sutun_sec(['B365>2.5', 'B365_O25', 'P>2.5', 'Max>2.5'])
    df['Open_U25'] = sutun_sec(['B365<2.5', 'B365_U25', 'P<2.5', 'Max<2.5'])
    
    # 2. Daha Güvenli Tekilleştirme (Oranlara göre değil, takımlara ve tarihe göre)
    if 'Date' in df.columns:
        df = df.drop_duplicates(subset=['HomeTeam', 'AwayTeam', 'Date'])
    else:
        df = df.drop_duplicates(subset=['HomeTeam', 'AwayTeam', 'FTHG', 'FTAG'])
    
    margin = (1 / df['Open_H']) + (1 / df['Open_D']) + (1 / df['Open_A'])
    df['pH'] = (1 / df['Open_H']) / margin
    df['pD'] = (1 / df['Open_D']) / margin
    df['pA'] = (1 / df['Open_A']) / margin
    
    # Alt oranı sistemde varsa gerçek marjı, yoksa %6 standart marjı kullan
    df['pOver'] = np.where(df['Open_U25'].notna(), 
                           (1 / df['Open_O25']) / ((1 / df['Open_O25']) + (1 / df['Open_U25'])), 
                           (1 / df['Open_O25']) / 1.06)
    
    # 3. GADDAR SİLME İŞLEMİ YUMUŞATILDI: Yalnızca algoritma için hayati olanları filtrele
    df = df.dropna(subset=['pH', 'pD', 'pA', 'pOver', 'FTHG', 'FTAG'])
    
    features = ['pH', 'pD', 'pA', 'pOver']
    X = df[features].values
    
    knn = NearestNeighbors(n_neighbors=50, metric='euclidean')
    knn.fit(X)
    return df, knn, features

def analiz_et(ph, pd_oran, pa, pover):
    sorgu = np.array([[ph, pd_oran, pa, pover]])
    mesafeler, indeksler = knn.kneighbors(sorgu)
    hedef_maclar = df.iloc[indeksler[0]].copy()
    
    df_takip = takip_dosyasi_yukle()
    tamamlananlar = df_takip[df_takip['Durum'] == 'Tamamlandı']
    trend_bonus = 1.04 if len(tamamlananlar) > 0 else 1.00
    
    res_map = {'H': 'MS 1', 'D': 'MS 0', 'A': 'MS 2'}
    hedef_maclar['MS_Kod'] = hedef_maclar['res'].map(res_map)
    ms_oranlari = (hedef_maclar['MS_Kod'].value_counts(normalize=True) * 100 * trend_bonus).round(1).to_dict()
    
    hedef_maclar['KG'] = (hedef_maclar['FTHG'] > 0) & (hedef_maclar['FTAG'] > 0)
    kg_yuzdesi = min(round(hedef_maclar['KG'].mean() * 100, 1), 98.0)
    ust_yuzdesi = min(round((hedef_maclar['tot'] > 2.5).mean() * 100, 1), 98.0)

    iki_yari_15_ust_yuzdesi = round(hedef_maclar['HT_Total'].ge(2).mean() * hedef_maclar['SH_Total'].ge(2).mean() * 100, 1)
    
    ht_kg_serisi = (hedef_maclar['HTHG'] > 0) & (hedef_maclar['HTAG'] > 0)
    sh_kg_serisi = (hedef_maclar['SH_Home'] > 0) & (hedef_maclar['SH_Away'] > 0)
    iki_yari_kg_yuzdesi = round((ht_kg_serisi & sh_kg_serisi).mean() * 100, 1)
    
    genel_iki_yari_15_ortalama = round(df['HT_Total'].ge(2).mean() * df['SH_Total'].ge(2).mean() * 100, 1)
    genel_ht_kg = (df['HTHG'] > 0) & (df['HTAG'] > 0)
    genel_sh_kg = (df['SH_Home'] > 0) & (df['SH_Away'] > 0)
    genel_iki_yari_kg_ortalama = round((genel_ht_kg & genel_sh_kg).mean() * 100, 1)
    
    fark_iki_yari_15 = round(iki_yari_15_ust_yuzdesi - genel_iki_yari_15_ortalama, 1)
    fark_iki_yari_kg = round(iki_yari_kg_yuzdesi - genel_iki_yari_kg_ortalama, 1)

    hedef_maclar['IY_Kod'] = np.where(hedef_maclar['HTHG'] > hedef_maclar['HTAG'], '1', 
                             np.where(hedef_maclar['HTHG'] < hedef_maclar['HTAG'], '2', '0'))
    ms_kisa_map = {'H': '1', 'D': '0', 'A': '2'}
    hedef_maclar['MS_Kisa'] = hedef_maclar['res'].map(ms_kisa_map)
    hedef_maclar['IY_MS'] = hedef_maclar['IY_Kod'] + "/" + hedef_maclar['MS_Kisa']
    
    tum_ihtimaller = {'1/1': 0.0, '1/0': 0.0, '1/2': 0.0, '0/1': 0.0, '0/0': 0.0, '0/2': 0.0, '2/1': 0.0, '2/0': 0.0, '2/2': 0.0}
    hesaplanan_oranlar = (hedef_maclar['IY_MS'].value_counts(normalize=True) * 100).round(1).to_dict()
    tum_ihtimaller.update(hesaplanan_oranlar)
    iy_ms_oranlari = tum_ihtimaller
    
    avg_corner = round(hedef_maclar['HC'].fillna(0).mean() + hedef_maclar['AC'].fillna(0).mean(), 1)
    avg_shot = round(hedef_maclar['HS'].fillna(0).mean() + hedef_maclar['AS'].fillna(0).mean(), 1)
    avg_ht_goal = round(hedef_maclar['HT_Total'].mean(), 2)
    avg_sh_goal = round(hedef_maclar['SH_Total'].mean(), 2)
    
    stats = {
        'korner': avg_corner if avg_corner > 0 else 9.5,
        'sut': avg_shot if avg_shot > 0 else 24.0,
        'iy_gol': avg_ht_goal,
        'ikinci_yari_gol': avg_sh_goal
    }
    
    tablo_df = hedef_maclar[['Date', 'Mac', 'Open_H', 'Open_D', 'Open_A', 'Open_O25', 'HTHG', 'HTAG', 'FTHG', 'FTAG', 'MS_Kod', 'IY_MS']].copy()
    tablo_df['HTHG'] = tablo_df['HTHG'].fillna(0).astype(int)
    tablo_df['HTAG'] = tablo_df['HTAG'].fillna(0).astype(int)
    tablo_df['FTHG'] = tablo_df['FTHG'].fillna(0).astype(int)
    tablo_df['FTAG'] = tablo_df['FTAG'].fillna(0).astype(int)
    tablo_df['İlk Yarı Skoru'] = tablo_df['HTHG'].astype(str) + " - " + tablo_df['HTAG'].astype(str)
    tablo_df['Maç Sonu Skoru'] = tablo_df['FTHG'].astype(str) + " - " + tablo_df['FTAG'].astype(str)
    tablo_df = tablo_df.rename(columns={'Date': 'Tarih', 'Mac': 'Maç', 'Open_H': 'Oran 1', 'Open_D': 'Oran X', 'Open_A': 'Oran 2', 'Open_O25': 'Oran Üst', 'MS_Kod': 'Sonuç', 'IY_MS': 'İY/MS'})[['Tarih', 'Maç', 'Oran 1', 'Oran X', 'Oran 2', 'Oran Üst', 'İlk Yarı Skoru', 'Maç Sonu Skoru', 'Sonuç', 'İY/MS']]

    return ms_oranlari, kg_yuzdesi, ust_yuzdesi, tablo_df, iy_ms_oranlari, iki_yari_15_ust_yuzdesi, iki_yari_kg_yuzdesi, fark_iki_yari_15, fark_iki_yari_kg, stats

def beklenen_deger_hesapla(oran, ihtimal_yuzdesi):
    ihtimal = ihtimal_yuzdesi / 100
    return round((ihtimal * oran) - 1, 3)

# --- SCRAPING MOTORU ---
@st.cache_data(ttl=1800)
def bulteni_kazi():
    cekilen_maclar = {"Manuel Giriş (Özel Maç Tanımla)": {"ms1": 2.10, "ms0": 3.20, "ms2": 2.90, "ust": 1.70, "kg": 1.55}}
    url = "https://arsiv.mackolik.com/Iddaa-Programi"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        basarili_veri = 0
        rows = soup.find_all('tr')
        for row in rows:
            ms1_tag = row.find('a', class_='MS1')
            if ms1_tag:
                try:
                    ms1 = float(ms1_tag.text.strip().replace(',', '.'))
                    ms0_tag = row.find('a', class_='MSX')
                    ms2_tag = row.find('a', class_='MS2')
                    ust_tag = row.find('a', class_='AU2') 
                    ms0 = float(ms0_tag.text.strip().replace(',', '.')) if ms0_tag and ms0_tag.text.strip() != '-' else 1.01
                    ms2 = float(ms2_tag.text.strip().replace(',', '.')) if ms2_tag and ms2_tag.text.strip() != '-' else 1.01
                    ust = float(ust_tag.text.strip().replace(',', '.')) if ust_tag and ust_tag.text.strip() != '-' else 1.01
                    
                    # GELİŞTİRİLMİŞ KG YAKALAYICI
                    kg = 1.55 
                    kg_tag = row.find('a', class_=lambda x: x and ('KG' in x.upper() or 'GOL' in x.upper()))
                    if kg_tag and kg_tag.text.strip() != '-':
                        try: kg = float(kg_tag.text.strip().replace(',', '.'))
                        except: pass
                    else:
                        tds = row.find_all('td')
                        for td in tds:
                            try:
                                val = float(td.text.strip().replace(',', '.'))
                                if 1.20 <= val <= 3.00 and val != ms1 and val != ust:
                                    kg = val; break
                            except: continue

                    if ms1 == 1.01 and ms0 == 1.01: continue
                    takim_adi = "Bilinmeyen Maç"
                    for td in row.find_all('td'):
                        if " - " in td.text and len(td.text.strip()) > 5:
                            takim_adi = " ".join(td.text.strip().split())
                            break
                    cekilen_maclar[takim_adi] = {"ms1": ms1, "ms0": ms0, "ms2": ms2, "ust": ust, "kg": kg}
                    basarili_veri += 1
                except: continue
        if basarili_veri == 0: raise ValueError("Boş")
    except:
        st.sidebar.warning("⚠️ Canlı bülten alınamadı. Standart mod aktif.")
    return cekilen_maclar

# --- KULLANICI ARAYÜZÜ (UI) ---
st.title("⚽ MacApp Pro | AI Trading & Risk Terminal")

arsiv_boyutu_str = f"{len(df):,}".replace(",", ".")
st.markdown(f"*(**{arsiv_boyutu_str}** maçlık canlı makine öğrenmesi arşivi ve Google Sheets entegre hafızası devrede)*")

st.sidebar.header("🌐 Bülten & Maç Seçimi")
guncel_bulten = bulteni_kazi()
secilen_mac = st.sidebar.selectbox("Bültenden Maç Seç:", list(guncel_bulten.keys()))
secili_oranlar = guncel_bulten[secilen_mac]

st.sidebar.markdown("---")
st.sidebar.header("📊 Oran Parametreleri")
ms1_oran = st.sidebar.number_input("MS 1 Oranı", min_value=1.01, max_value=50.0, value=float(secili_oranlar["ms1"]), step=0.01, format="%.2f")
ms0_oran = st.sidebar.number_input("MS X Oranı", min_value=1.01, max_value=50.0, value=float(secili_oranlar["ms0"]), step=0.01, format="%.2f")
ms2_oran = st.sidebar.number_input("MS 2 Oranı", min_value=1.01, max_value=50.0, value=float(secili_oranlar["ms2"]), step=0.01, format="%.2f")
ust_oran = st.sidebar.number_input("2.5 Üst Oranı", min_value=1.01, max_value=50.0, value=float(secili_oranlar["ust"]), step=0.01, format="%.2f")
kg_oran = st.sidebar.number_input("KG Var Oranı", min_value=1.01, max_value=50.0, value=float(secili_oranlar["kg"]), step=0.01, format="%.2f")

st.sidebar.markdown("---")
st.sidebar.header("💰 Risk & Kasa Yönetimi")
bakiye = st.sidebar.number_input("Toplam Kasa (TL)", min_value=10, value=1000, step=100)
bahis_miktari = st.sidebar.number_input("Bahis Miktarı (TL)", min_value=1, value=100, step=10)

taraf_marj = (1 / ms1_oran) + (1 / ms0_oran) + (1 / ms2_oran)
ph_gercek = (1 / ms1_oran) / taraf_marj
pd_gercek = (1 / ms0_oran) / taraf_marj
pa_gercek = (1 / ms2_oran) / taraf_marj
pover_gercek = (1 / ust_oran) / 1.06

if st.sidebar.button("🚀 Yapay Zeka Analizini Başlat", use_container_width=True):
    with st.spinner("Model benzer tarihi maçları tarıyor ve risk hesaplıyor..."):
        ms, kg_yuzdesi, ust_yuzdesi, benzer_maclar, iy_ms, iki_yari_15_ust, iki_yari_kg, fark_15, fark_kg, stats = analiz_et(ph_gercek, pd_gercek, pa_gercek, pover_gercek)
        st.session_state.update({
            'analiz_tamam': True, 'ms': ms, 'kg_yuzdesi': kg_yuzdesi, 'ust_yuzdesi': ust_yuzdesi,
            'benzer_maclar': benzer_maclar, 'iy_ms': iy_ms, 'iki_yari_15_ust': iki_yari_15_ust,
            'iki_yari_kg': iki_yari_kg, 'fark_15': fark_15, 'fark_kg': fark_kg, 'stats': stats, 'secilen_mac_baslik': secilen_mac
        })

if st.session_state.get('analiz_tamam', False):
    ms = st.session_state['ms']
    kg_yuzdesi = st.session_state['kg_yuzdesi']
    ust_yuzdesi = st.session_state['ust_yuzdesi']
    stats = st.session_state['stats']
    iy_ms = st.session_state['iy_ms']
    aktif_mac = st.session_state.get('secilen_mac_baslik', 'Özel Maç')
    
    # YENİ 4 SEKME (Nokta Atışı Filtresi Eklendi)
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Görsel Trading Dashboard", 
        "🎯 Nokta Atışı Özel Oran Tarayıcı",
        "💰 ROI & Value Bet Analizi", 
        "📈 Tahmin Takibi & Öğrenen Karne"
    ])
    
    ev_dict = {
        "MS 1": {"prob": ms.get('MS 1', 0), "oran": ms1_oran, "ev": beklenen_deger_hesapla(ms1_oran, ms.get('MS 1', 0))},
        "MS 0": {"prob": ms.get('MS 0', 0), "oran": ms0_oran, "ev": beklenen_deger_hesapla(ms0_oran, ms.get('MS 0', 0))},
        "MS 2": {"prob": ms.get('MS 2', 0), "oran": ms2_oran, "ev": beklenen_deger_hesapla(ms2_oran, ms.get('MS 2', 0))},
        "2.5 ÜST": {"prob": ust_yuzdesi, "oran": ust_oran, "ev": beklenen_deger_hesapla(ust_oran, ust_yuzdesi)},
        "KG VAR": {"prob": kg_yuzdesi, "oran": kg_oran, "ev": beklenen_deger_hesapla(kg_oran, kg_yuzdesi)}
    }
    
    en_degerli_isim = max(ev_dict, key=lambda x: ev_dict[x]['ev'])
    en_degerli_ev = ev_dict[en_degerli_isim]['ev']
    banko_isim = max(ev_dict, key=lambda x: ev_dict[x]['prob'])
    banko_oran = ev_dict[banko_isim]['oran']
    ideal_isim = en_degerli_isim if en_degerli_ev > 0 else "Pas Geç"
    ideal_oran = ev_dict[en_degerli_isim]['oran'] if en_degerli_ev > 0 else 0.0
    
    en_yuksek_iyms = max(iy_ms, key=iy_ms.get)
    iyms_oran_tahmin = round((100 / (iy_ms[en_yuksek_iyms] if iy_ms[en_yuksek_iyms] > 0 else 1.1)) * 0.85, 2)
    
    ters_iyms = {k: v for k, v in iy_ms.items() if k in ['1/2', '2/1'] and v > 0}
    if ters_iyms:
        surpriz_isim = max(ters_iyms, key=ters_iyms.get) + " (Dönüş)"
        surpriz_oran = round((100 / ters_iyms[surpriz_isim[:3]]) * 0.85, 2)
    elif st.session_state['iki_yari_15_ust'] > 8:
        surpriz_isim = "İki Yarı 1.5 Üst"
        surpriz_oran = round((100 / st.session_state['iki_yari_15_ust']) * 0.85, 2)
    else:
        surpriz_isim = "MS 0"
        surpriz_oran = ms0_oran

    # --- TAB 1: DASHBOARD ---
    with tab1:
        st.subheader("🎯 Olasılık Dağılımı ve Piyasa Analizi (KNN 50 Maç)")
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("MS 1 Olasılığı", f"%{ms.get('MS 1', 0)}", f"Oran: {ms1_oran}")
        col_m2.metric("MS X Olasılığı", f"%{ms.get('MS 0', 0)}", f"Oran: {ms0_oran}")
        col_m3.metric("MS 2 Olasılığı", f"%{ms.get('MS 2', 0)}", f"Oran: {ms2_oran}")
        
        st.markdown("---")
        c_g1, c_g2 = st.columns(2)
        with c_g1:
            st.markdown("#### ⚽ Gol & Karşılıklı Gol Eğilimi")
            st.progress(int(kg_yuzdesi))
            st.write(f"**KG VAR İhtimali:** %{kg_yuzdesi}")
            st.progress(int(ust_yuzdesi))
            st.write(f"**2.5 ÜST İhtimali:** %{ust_yuzdesi}")
        with c_g2:
            st.markdown("#### 🏃‍♂️ Saha İçi Beklentiler (Ortalama)")
            st.info(f"⚡ **Beklenen Şut:** {stats['sut']} Şut\n\n🚩 **Beklenen Korner:** {stats['korner']} Korner\n\n⏱️ **İlk Yarı Gol:** {stats['iy_gol']} | **2. Yarı Gol:** {stats['ikinci_yari_gol']}")

        st.markdown("---")
        st.subheader("🧪 İY/MS Matrisi & İki Yarı Özel Karşılaştırma Farkları")
        
        f_col1, f_col2 = st.columns(2)
        f_col1.metric("İki Yarıda da 1.5 Üst Olasılığı", f"%{st.session_state['iki_yari_15_ust']}", f"{st.session_state['fark_15']:+.1f}% (Genel Ortalamaya Göre)")
        f_col2.metric("İki Yarıda da KG Var Olasılığı", f"%{st.session_state['iki_yari_kg']}", f"{st.session_state['fark_kg']:+.1f}% (Genel Ortalamaya Göre)")

        with st.expander("📋 Detaylı İY/MS Olasılık Matrisini Gör"):
            iy_ms_df = pd.DataFrame(list(iy_ms.items()), columns=['İY/MS Senaryosu', 'Gerçekleşme (%)']).sort_values(by='Gerçekleşme (%)', ascending=False).reset_index(drop=True)
            st.dataframe(iy_ms_df, use_container_width=True)

        st.markdown("---")
        st.subheader("🔍 Benzer 50 Maçlık Arşiv Filtresi ve İY/MS Arama")
        
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1: 
            ms_filtre = st.multiselect("Sonuç Filtrele", options=["MS 1", "MS 0", "MS 2"], default=["MS 1", "MS 0", "MS 2"])
        with col_f2:
            iyms_secenekler = list(iy_ms.keys())
            iyms_filtre = st.multiselect("İY/MS Kombinasyon Filtrele", options=iyms_secenekler, default=iyms_secenekler)
        with col_f3: 
            goster_sayi = st.slider("Kayıt Sayısı", 5, 50, 10, 5)
        
        ham_benzer = st.session_state['benzer_maclar']
        filtreli_df = ham_benzer[ham_benzer['Sonuç'].isin(ms_filtre) & ham_benzer['İY/MS'].isin(iyms_filtre)]
        st.dataframe(filtreli_df.head(goster_sayi), use_container_width=True)

    # --- TAB 2: NOKTA ATIŞI ÖZEL ORAN TARAYICI (Gelişmiş Çoklu Market & Büro Filtresi) ---
    with tab2:
        st.subheader("🎯 Çoklu Büro ve Genişletilmiş Market Oran Tarayıcı")
        st.markdown("Arşivdeki **Bet365** veya **Pinnacle** sağlayıcılarının oranlarını seçip, **8 farklı bahis marketi** üzerinden birebir veya toleranslı eşleşme araması yapabilirsin.")

        c_buro, c_tol = st.columns([1, 1])
        with c_buro:
            secili_buro = st.radio("🏢 Sağlayıcı (Büro) Seçimi:", ["Bet365", "Pinnacle"], horizontal=True)
        with c_tol:
            tolerans = st.slider("🎯 Hassasiyet Toleransı (±)", min_value=0.0, max_value=0.20, value=0.05, step=0.01, help="Örn: 2.10 oran için ±0.05 tolerans, 2.05 ile 2.15 arasındaki tüm maçları getirir.")

        st.markdown("---")
        st.markdown(f"### 📊 {secili_buro} Oran Kriterleri & Market Seçimi")
        
        # Müşterek Oran Değerleri
        ornek_oranlar = {
            "MS 1": float(ms1_oran),
            "MS X": float(ms0_oran),
            "MS 2": float(ms2_oran),
            "2.5 Üst": float(ust_oran),
            "2.5 Alt": 1.95,
            "1.5 Üst": 1.25,
            "KG Var": float(kg_oran),
            "İY 1": 2.75
        }

        # Market Seçim Kutuları (8 Farklı Market)
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m5, col_m6, col_m7, col_m8 = st.columns(4)

        secimler = {}
        secimler["MS 1"] = col_m1.checkbox(f"MS 1 ({ornek_oranlar['MS 1']:.2f})", value=True)
        secimler["MS X"] = col_m2.checkbox(f"MS X ({ornek_oranlar['MS X']:.2f})", value=False)
        secimler["MS 2"] = col_m3.checkbox(f"MS 2 ({ornek_oranlar['MS 2']:.2f})", value=False)
        secimler["2.5 Üst"] = col_m4.checkbox(f"2.5 Üst ({ornek_oranlar['2.5 Üst']:.2f})", value=True)

        secimler["2.5 Alt"] = col_m5.checkbox("2.5 Alt", value=False)
        secimler["1.5 Üst"] = col_m6.checkbox("1.5 Üst", value=False)
        secimler["KG Var"] = col_m7.checkbox(f"KG Var ({ornek_oranlar['KG Var']:.2f})", value=False)
        secimler["İY 1"] = col_m8.checkbox("İY 1 (İlk Yarı)", value=False)

        # Aktif Edilen Kriterleri Toplama ve Veri Seti Sütunlarıyla Eşleştirme
        aktif_kriterler = {}
        for market, aktif in secimler.items():
            if aktif:
                sutun_adi = sutun_getir(df, BURO_MAP[secili_buro][market])
                if sutun_adi:
                    aktif_kriterler[market] = {
                        "sutun": sutun_adi,
                        "deger": ornek_oranlar[market]
                    }
                else:
                    st.warning(f"⚠️ {secili_buro} için '{market}' sütunu veritabanında bulunamadı, bu kriter atlanacak.")

        if st.button(f"🔍 {secili_buro} Veritabanını Bu Marketlerle Tara", use_container_width=True):
            if not aktif_kriterler:
                st.warning("Lütfen arama yapmak için en az bir aktif bahis marketi seçin.")
            else:
                with st.spinner(f"{secili_buro} oranları taranıyor..."):
                    filtre = pd.Series(True, index=df.index)
                    for market, veri in aktif_kriterler.items():
                        s_col = veri["sutun"]
                        s_val = veri["deger"]
                        filtre &= df[s_col].between(s_val - tolerans, s_val + tolerans)

                    bulunan_maclar = df[filtre].copy()

                    if len(bulunan_maclar) == 0:
                        st.warning(f"⚠️ {secili_buro} tarafında bu oran kombinasyonuna sahip geçmiş maç bulunamadı. Toleransı (±) artırmayı veya daha az filtre seçmeyi deneyin.")
                    else:
                        st.success(f"✅ Toplam **{len(bulunan_maclar)}** eşleşen maç bulundu! ({secili_buro} Oranlarıyla)")

                        # İstatistik Hesaplamaları
                        b_ms1 = len(bulunan_maclar[bulunan_maclar['res'] == 'H'])
                        b_ms0 = len(bulunan_maclar[bulunan_maclar['res'] == 'D'])
                        b_ms2 = len(bulunan_maclar[bulunan_maclar['res'] == 'A'])
                        b_ust25 = len(bulunan_maclar[bulunan_maclar['tot'] > 2.5])
                        b_kg = len(bulunan_maclar[(bulunan_maclar['FTHG'] > 0) & (bulunan_maclar['FTAG'] > 0)])
                        
                        b_1X = len(bulunan_maclar[bulunan_maclar['res'].isin(['H', 'D'])])
                        b_12 = len(bulunan_maclar[bulunan_maclar['res'].isin(['H', 'A'])])
                        b_02 = len(bulunan_maclar[bulunan_maclar['res'].isin(['D', 'A'])])
                        b_iy05 = len(bulunan_maclar[(bulunan_maclar['HTHG'] + bulunan_maclar['HTAG']) > 0])
                        b_iy15 = len(bulunan_maclar[(bulunan_maclar['HTHG'] + bulunan_maclar['HTAG']) > 1])
                        b_ust35 = len(bulunan_maclar[bulunan_maclar['tot'] > 3.5])

                        # Metrik Gösterimleri
                        st.markdown("#### 🏆 Maç Sonu & Gol Dağılım Oranları")
                        m1, m2, m3, m4, m5, m6 = st.columns(6)
                        m1.metric("MS 1", f"%{round((b_ms1/len(bulunan_maclar))*100,1)}")
                        m2.metric("MS X", f"%{round((b_ms0/len(bulunan_maclar))*100,1)}")
                        m3.metric("MS 2", f"%{round((b_ms2/len(bulunan_maclar))*100,1)}")
                        m4.metric("2.5 ÜST", f"%{round((b_ust25/len(bulunan_maclar))*100,1)}")
                        m5.metric("3.5 ÜST", f"%{round((b_ust35/len(bulunan_maclar))*100,1)}")
                        m6.metric("KG VAR", f"%{round((b_kg/len(bulunan_maclar))*100,1)}")

                        st.markdown("#### 🛡️ Çifte Şans & İY Gol Detayları")
                        e1, e2, e3, e4, e5 = st.columns(5)
                        e1.metric("1X Çifte Şans", f"%{round((b_1X/len(bulunan_maclar))*100,1)}")
                        e2.metric("12 Çifte Şans", f"%{round((b_12/len(bulunan_maclar))*100,1)}")
                        e3.metric("X2 Çifte Şans", f"%{round((b_02/len(bulunan_maclar))*100,1)}")
                        e4.metric("İY 0.5 ÜST", f"%{round((b_iy05/len(bulunan_maclar))*100,1)}")
                        e5.metric("İY 1.5 ÜST", f"%{round((b_iy15/len(bulunan_maclar))*100,1)}")

                        st.markdown("#### 📋 Eşleşen Maçların Detaylı Listesi")
                        
                        goster_sutunlar = ['Date', 'HomeTeam', 'AwayTeam', 'HTHG', 'HTAG', 'FTHG', 'FTAG']
                        for m_key, m_val in aktif_kriterler.items():
                            goster_sutunlar.append(m_val['sutun'])
                        
                        gosterge_df = bulunan_maclar[list(dict.fromkeys(goster_sutunlar))].copy()
                        gosterge_df['İY Skor'] = gosterge_df['HTHG'].fillna(0).astype(int).astype(str) + " - " + gosterge_df['HTAG'].fillna(0).astype(int).astype(str)
                        gosterge_df['MS Skor'] = gosterge_df['FTHG'].fillna(0).astype(int).astype(str) + " - " + gosterge_df['FTAG'].fillna(0).astype(int).astype(str)
                        
                        st.dataframe(gosterge_df, use_container_width=True)

    # --- TAB 3: ROI & KASA ---
    with tab3:
        st.subheader("💎 Value Bet & Beklenen Değer (EV) Hesaplayıcı")
        if en_degerli_ev > 0:
            st.success(f"🎯 **AVANTAJLI BAHİS (VALUE):** Büronun açığı **{en_degerli_isim}** tercihinde yakalandı! Beklenen Değer (EV): **+{en_degerli_ev}**")
        else:
            st.warning("⚠️ Bu maçta net bir value açığı bulunmuyor, oranlar adil.")

        st.markdown("### 📋 Yapay Zeka Öngörü Paketi")
        t1, t2 = st.columns(2)
        t3, t4 = st.columns(2)
        
        t1.info(f"🛡️ **BANKO TAHMİN**\n\n**{banko_isim}** (Oran: {banko_oran})")
        t2.success(f"💎 **İDEAL (VALUE)**\n\n**{ideal_isim}** (Oran: {ideal_oran})")
        t3.warning(f"⏱️ **İY/MS TAHMİN**\n\n**{en_yuksek_iyms}** (Oran: {iyms_oran_tahmin})")
        t4.error(f"🧨 **SÜRPRİZ**\n\n**{surpriz_isim}** (Oran: {surpriz_oran})")

        st.markdown("---")
        if st.button("📌 Bu Analizi ve 4 Tahmini Google Sheets'e Kaydet", use_container_width=True):
            df_takip = takip_dosyasi_yukle()
            yeni_id = len(df_takip) + 1 if not df_takip.empty else 1
            yeni_kayit = {
                'ID': yeni_id,
                'Tarih': pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
                'Mac': aktif_mac,
                'Banko_Tahmin': banko_isim, 'Banko_Oran': f"{banko_oran:.2f}",
                'Ideal_Tahmin': ideal_isim, 'Ideal_Oran': f"{ideal_oran:.2f}",
                'IYMS_Tahmin': en_yuksek_iyms, 'IYMS_Oran': f"{iyms_oran_tahmin:.2f}",
                'Surpriz_Tahmin': surpriz_isim, 'Surpriz_Oran': f"{surpriz_oran:.2f}",
                'IY_Skor': 'Oynanmadı', 'MS_Skor': 'Oynanmadı', 
                'Korner': '-', 'Sut': '-', 'Kart': '-', 'Durum': 'Bekliyor'
            }
            df_takip = pd.concat([df_takip, pd.DataFrame([yeni_kayit])], ignore_index=True)
            takip_dosyasi_kaydet(df_takip)
            st.toast("✅ Analiz kalıcı hafızaya kaydedildi!", icon="📌")

    # --- TAB 4: TAHMİN TAKİBİ ---
    with tab4:
        st.subheader("📈 Tahmin Takibi & Gelişmiş Sonuç / İstatistik Paneli")
        df_takip = takip_dosyasi_yukle()
        
        if len(df_takip) == 0:
            st.info("Kayıtlı veri bulunmuyor.")
        else:
            df_gosterge = df_takip.copy()
            for oran_sutun in ['Banko_Oran', 'Ideal_Oran', 'IYMS_Oran', 'Surpriz_Oran']:
                if oran_sutun in df_gosterge.columns:
                    df_gosterge[oran_sutun] = df_gosterge[oran_sutun].apply(oran_duzelt)

            tamamlananlar = df_gosterge[df_gosterge['Durum'] == 'Tamamlandı'].copy()
            b_hit, b_miss, i_hit, i_miss = 0, 0, 0, 0
            toplam_t = len(tamamlananlar)
            
            if toplam_t > 0:
                for idx, row in tamamlananlar.iterrows():
                    try:
                        iy_h, iy_a = map(int, str(row['IY_Skor']).split('-'))
                        ms_h, ms_a = map(int, str(row['MS_Skor']).split('-'))
                        ms_res = "MS 1" if ms_h > ms_a else ("MS 2" if ms_a > ms_h else "MS 0")
                        kg_res = "KG VAR" if (ms_h > 0 and ms_a > 0) else "KG YOK"
                        ust_res = "2.5 ÜST" if (ms_h + ms_a) > 2.5 else "2.5 ALT"
                        
                        if row['Banko_Tahmin'] in [ms_res, kg_res, ust_res]: b_hit += 1
                        else: b_miss += 1
                        if row['Ideal_Tahmin'] in [ms_res, kg_res, ust_res]: i_hit += 1
                        elif row['Ideal_Tahmin'] != "Pas Geç": i_miss += 1
                    except: pass

                m1, m2 = st.columns(2)
                m1.metric("Banko İsabet Oranı", f"%{round((b_hit/toplam_t)*100, 1) if toplam_t > 0 else 0}", f"✅ {b_hit} | ❌ {b_miss}")
                m2.metric("İdeal (Value) İsabet Oranı", f"%{round((i_hit/(i_hit+i_miss))*100, 1) if (i_hit+i_miss) > 0 else 0}", f"✅ {i_hit} | ❌ {i_miss}")
                st.markdown("---")

            st.markdown("### 📝 Google Sheets Veritabanı Tablosu")
            def highlight_status(val):
                return f"color: {'#1f77b4' if val == 'Bekliyor' else '#2ca02c'}; font-weight: bold"
            st.dataframe(df_gosterge.style.map(highlight_status, subset=['Durum']), use_container_width=True)
            
            st.markdown("#### ⚽ Maç Sonucu, Skor ve Detaylı Saha İçi İstatistikleri Gir")
            bekleyenler = df_takip[df_takip['Durum'] == 'Bekliyor']
            if len(bekleyenler) > 0:
                c_s1, c_s2, c_s3 = st.columns([2, 1, 1])
                secili_id = c_s1.selectbox("Sonuçlandırılacak Maçı Seç:", bekleyenler['ID'].tolist(), format_func=lambda x: f"ID {x}: {df_takip.loc[df_takip['ID']==x, 'Mac'].values[0]}")
                iy_skor_gir = c_s2.text_input("İY Skoru (Örn: 1-0):", value="0-0")
                ms_skor_gir = c_s3.text_input("MS Skoru (Örn: 2-1):", value="1-1")
                
                c_i1, c_i2, c_i3, c_btn = st.columns([1, 1, 1, 1.5])
                korner_gir = c_i1.text_input("Toplam Korner:", value="9")
                sut_gir = c_i2.text_input("Toplam Şut:", value="22")
                kart_gir = c_i3.text_input("Sarı/Kırmızı Kart:", value="4")
                
                c_btn.markdown("<br>", unsafe_allow_html=True) 
                if c_btn.button("💾 Tüm Verileri ve İstatistikleri Onayla"):
                    df_takip.loc[df_takip['ID'] == secili_id, 'IY_Skor'] = iy_skor_gir
                    df_takip.loc[df_takip['ID'] == secili_id, 'MS_Skor'] = ms_skor_gir
                    df_takip.loc[df_takip['ID'] == secili_id, 'Korner'] = korner_gir
                    df_takip.loc[df_takip['ID'] == secili_id, 'Sut'] = sut_gir
                    df_takip.loc[df_takip['ID'] == secili_id, 'Kart'] = kart_gir
                    df_takip.loc[df_takip['ID'] == secili_id, 'Durum'] = 'Tamamlandı'
                    takip_dosyasi_kaydet(df_takip)
                    st.success("İstatistikler ve maç sonucu Google Sheets veritabanına işlendi!")
                    st.rerun()
            else:
                st.info("🎉 Bekleyen maçınız bulunmuyor.")
