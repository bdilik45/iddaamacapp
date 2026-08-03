import streamlit as st
import pandas as pd
import numpy as np
from sklearn.neighbors import NearestNeighbors
import requests
from bs4 import BeautifulSoup
import os
import warnings
warnings.filterwarnings('ignore')

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="MacApp Pro", page_icon="⚽", layout="wide")

# Kayıt Dosyası Adı
TAKIP_DOSYASI = "tahmin_gecmisi.csv"

def takip_dosyasi_yukle():
    if os.path.exists(TAKIP_DOSYASI):
        return pd.read_csv(TAKIP_DOSYASI)
    else:
        return pd.DataFrame(columns=[
            'ID', 'Tarih', 'Mac', 'Banko_Tahmin', 'Banko_Oran', 
            'Ideal_Tahmin', 'Ideal_Oran', 'IYMS_Tahmin', 'IYMS_Oran', 
            'Surpriz_Tahmin', 'Surpriz_Oran', 'IY_Skor', 'MS_Skor', 'Durum'
        ])

def takip_dosyasi_kaydet(df_takip):
    df_takip.to_csv(TAKIP_DOSYASI, index=False)

# --- YAPAY ZEKA MOTORU ---
@st.cache_resource
def motoru_baslat():
    veri_yolu = "iddaa_arsiv_YEDEK.parquet" 
    df = pd.read_parquet(veri_yolu)
    
    # 1. Başlıkları Çevir
    df['Mac'] = df['HomeTeam'] + " - " + df['AwayTeam']
    df['res'] = df['FTR']  
    df['tot'] = df['FTHG'] + df['FTAG']  
    
    df['Open_H'] = df['B365H']
    df['Open_D'] = df['B365D']
    df['Open_A'] = df['B365A']
    df['Open_O25'] = df['B365>2.5']
    
    # 2. Temizlik
    df = df.drop_duplicates(subset=['HomeTeam', 'AwayTeam', 'FTHG', 'FTAG', 'Open_H', 'Open_D'])
    
    # 3. Olasılık Hesaplama
    margin = (1 / df['Open_H']) + (1 / df['Open_D']) + (1 / df['Open_A'])
    df['pH'] = (1 / df['Open_H']) / margin
    df['pD'] = (1 / df['Open_D']) / margin
    df['pA'] = (1 / df['Open_A']) / margin
    
    margin_ou = (1 / df['B365>2.5']) + (1 / df['B365<2.5'])
    df['pOver'] = (1 / df['B365>2.5']) / margin_ou
    
    df = df.dropna(subset=['pH', 'pD', 'pA', 'pOver', 'FTHG', 'FTAG', 'HTHG', 'HTAG', 'Open_H', 'Open_D', 'Open_A', 'Open_O25', 'res'])
    
    features = ['pH', 'pD', 'pA', 'pOver']
    X = df[features].values
    knn = NearestNeighbors(n_neighbors=50, metric='euclidean')
    knn.fit(X)
    return df, knn, features

try:
    df, knn, features = motoru_baslat()
except Exception as e:
    st.error(f"Veri seti yüklenirken hata oluştu. Detay: {e}")
    st.stop()

def analiz_et(ph, pd_oran, pa, pover):
    sorgu = np.array([[ph, pd_oran, pa, pover]])
    mesafeler, indeksler = knn.kneighbors(sorgu)
    hedef_maclar = df.iloc[indeksler[0]].copy()
    
    res_map = {'H': 'MS 1', 'D': 'MS 0', 'A': 'MS 2'}
    hedef_maclar['MS_Kod'] = hedef_maclar['res'].map(res_map)
    ms_oranlari = (hedef_maclar['MS_Kod'].value_counts(normalize=True) * 100).round(1).to_dict()
    
    hedef_maclar['KG'] = (hedef_maclar['FTHG'] > 0) & (hedef_maclar['FTAG'] > 0)
    kg_yuzdesi = round(hedef_maclar['KG'].mean() * 100, 1)
    ust_yuzdesi = round((hedef_maclar['tot'] > 2.5).mean() * 100, 1)
    
    hedef_maclar['HT_Total'] = hedef_maclar['HTHG'] + hedef_maclar['HTAG']
    hedef_maclar['SH_Home'] = hedef_maclar['FTHG'] - hedef_maclar['HTHG']
    hedef_maclar['SH_Away'] = hedef_maclar['FTAG'] - hedef_maclar['HTAG']
    hedef_maclar['SH_Total'] = hedef_maclar['SH_Home'] + hedef_maclar['SH_Away']

    hedef_maclar['IkiYari_15Ust'] = (hedef_maclar['HT_Total'] >= 2) & (hedef_maclar['SH_Total'] >= 2)
    iki_yari_15_ust_yuzdesi = round(hedef_maclar['IkiYari_15Ust'].mean() * 100, 1)

    hedef_maclar['HT_KG'] = (hedef_maclar['HTHG'] > 0) & (hedef_maclar['HTAG'] > 0)
    hedef_maclar['SH_KG'] = (hedef_maclar['SH_Home'] > 0) & (hedef_maclar['SH_Away'] > 0)
    hedef_maclar['IkiYari_KG'] = hedef_maclar['HT_KG'] & hedef_maclar['SH_KG']
    iki_yari_kg_yuzdesi = round(hedef_maclar['IkiYari_KG'].mean() * 100, 1)
    
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
        'korner': avg_corner if avg_corner > 0 else "Alt Lig (Kayıt Yok)",
        'sut': avg_shot if avg_shot > 0 else "Alt Lig (Kayıt Yok)",
        'iy_gol': avg_ht_goal,
        'ikinci_yari_gol': avg_sh_goal
    }
    
    yildizlar = []
    ters_donus_oran = iy_ms_oranlari.get('1/2', 0.0) + iy_ms_oranlari.get('2/1', 0.0)
    if ters_donus_oran >= 6.0:
        yildizlar.append(f"🚨 İY/MS DÖNÜŞ POTANSİYELİ: Tarihsel olarak bu oranlarda 1/2 veya 2/1 gelme olasılığı %{ters_donus_oran}.")
    if kg_yuzdesi >= 68:
        yildizlar.append(f"🔥 YÜKSEK KG VAR EĞİLİMİ: Benzer 50 maçın %{kg_yuzdesi}'sinde Karşılıklı Gol oldu.")
    if ust_yuzdesi >= 70:
        yildizlar.append(f"📈 2.5 ÜST EĞİLİMİ: Geçmişte bu oran profilinin %{ust_yuzdesi}'si 2.5 ÜST bitti.")

    tablo_df = hedef_maclar[['Date', 'Mac', 'Open_H', 'Open_D', 'Open_A', 'Open_O25', 'HTHG', 'HTAG', 'FTHG', 'FTAG', 'MS_Kod', 'IY_MS']].copy()
    tablo_df['HTHG'] = tablo_df['HTHG'].fillna(0).astype(int)
    tablo_df['HTAG'] = tablo_df['HTAG'].fillna(0).astype(int)
    tablo_df['FTHG'] = tablo_df['FTHG'].fillna(0).astype(int)
    tablo_df['FTAG'] = tablo_df['FTAG'].fillna(0).astype(int)
    tablo_df['İlk Yarı Skoru'] = tablo_df['HTHG'].astype(str) + " - " + tablo_df['HTAG'].astype(str)
    tablo_df['Maç Sonu Skoru'] = tablo_df['FTHG'].astype(str) + " - " + tablo_df['FTAG'].astype(str)
    tablo_df = tablo_df.rename(columns={'Date': 'Tarih', 'Mac': 'Maç', 'Open_H': 'Oran 1', 'Open_D': 'Oran X', 'Open_A': 'Oran 2', 'Open_O25': 'Oran Üst', 'MS_Kod': 'Sonuç', 'IY_MS': 'İY/MS'})[['Tarih', 'Maç', 'Oran 1', 'Oran X', 'Oran 2', 'Oran Üst', 'İlk Yarı Skoru', 'Maç Sonu Skoru', 'Sonuç', 'İY/MS']]

    return ms_oranlari, kg_yuzdesi, ust_yuzdesi, yildizlar, tablo_df, iy_ms_oranlari, iki_yari_15_ust_yuzdesi, iki_yari_kg_yuzdesi, stats

def beklenen_deger_hesapla(oran, ihtimal_yuzdesi):
    ihtimal = ihtimal_yuzdesi / 100
    return round((ihtimal * oran) - 1, 3)

# --- WEB SCRAPING MOTORU ---
@st.cache_data(ttl=1800)
def bulteni_kazi():
    cekilen_maclar = {"Manuel Giriş (Kendim Yazacağım)": {"ms1": 1.92, "ms0": 3.01, "ms2": 2.86, "ust": 1.60, "kg": 1.48}}
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
                    kg = 1.50 
                    if ms1 == 1.01 and ms0 == 1.01: continue
                    takim_adi = "Bilinmeyen Maç"
                    tds = row.find_all('td')
                    for td in tds:
                        if " - " in td.text and len(td.text.strip()) > 5:
                            takim_adi = " ".join(td.text.strip().split())
                            break
                    cekilen_maclar[takim_adi] = {"ms1": ms1, "ms0": ms0, "ms2": ms2, "ust": ust, "kg": kg}
                    basarili_veri += 1
                except: continue
        if basarili_veri == 0: raise ValueError("Boş")
    except:
        st.sidebar.warning("⚠️ Canlı veri çekilemedi. Yedek bülten devrede.")
    return cekilen_maclar

# --- WEB ARAYÜZÜ ---
st.title("⚽ MacApp Pro | Analiz & Yatırım Terminali")
st.markdown(f"*(**{len(df)}** maçlık devasa makine öğrenmesi veritabanı aktif)*")

st.sidebar.header("🌐 Canlı Bülten (Mackolik)")
guncel_bulten = bulteni_kazi()
secilen_mac = st.sidebar.selectbox("Analiz Edilecek Maçı Seçin:", list(guncel_bulten.keys()))
secili_oranlar = guncel_bulten[secilen_mac]

st.sidebar.markdown("---")
st.sidebar.header("Maç Oranları")
ms1_oran = st.sidebar.number_input("MS 1 Oranı", min_value=1.01, value=float(secili_oranlar["ms1"]), step=0.05)
ms0_oran = st.sidebar.number_input("MS X (Beraberlik)", min_value=1.01, value=float(secili_oranlar["ms0"]), step=0.05)
ms2_oran = st.sidebar.number_input("MS 2 Oranı", min_value=1.01, value=float(secili_oranlar["ms2"]), step=0.05)
ust_oran = st.sidebar.number_input("2.5 Üst Oranı", min_value=1.01, value=float(secili_oranlar["ust"]), step=0.05)
kg_oran = st.sidebar.number_input("KG Var Oranı", min_value=1.01, value=float(secili_oranlar["kg"]), step=0.05)

st.sidebar.markdown("---")
st.sidebar.header("Kasa Yönetimi")
bakiye = st.sidebar.number_input("Mevcut Kasa (TL)", min_value=10, value=1000, step=100)
bahis_miktari = st.sidebar.number_input("Yatırılacak Miktar (TL)", min_value=1, value=100, step=10)

taraf_marj = (1 / ms1_oran) + (1 / ms0_oran) + (1 / ms2_oran)
ph_gercek = (1 / ms1_oran) / taraf_marj
pd_gercek = (1 / ms0_oran) / taraf_marj
pa_gercek = (1 / ms2_oran) / taraf_marj
pover_gercek = (1 / ust_oran) / 1.07

if st.sidebar.button("🔍 Yapay Zeka Analizini Başlat"):
    with st.spinner("MacApp geçmiş verileri tarıyor..."):
        ms, kg, ust, yildizlar, benzer_maclar, iy_ms, iki_yari_15_ust, iki_yari_kg, stats = analiz_et(ph_gercek, pd_gercek, pa_gercek, pover_gercek)
        st.session_state.update({
            'analiz_tamam': True, 'ms': ms, 'kg': kg, 'ust': ust, 'yildizlar': yildizlar,
            'benzer_maclar': benzer_maclar, 'iy_ms': iy_ms, 'iki_yari_15_ust': iki_yari_15_ust,
            'iki_yari_kg': iki_yari_kg, 'stats': stats, 'secilen_mac_baslik': secilen_mac
        })

if st.session_state.get('analiz_tamam', False):
    ms = st.session_state['ms']
    kg = st.session_state['kg']
    ust = st.session_state['ust']
    stats = st.session_state['stats']
    iy_ms = st.session_state['iy_ms']
    aktif_mac = st.session_state.get('secilen_mac_baslik', 'Manuel Maç')
    
    # SEKMELER (4. Sekme eklendi)
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Görsel Dashboard", 
        "🧪 Backtest", 
        "💰 ROI & Kasa Yönetimi", 
        "📈 Tahmin Takibi & Başarı Karnesi"
    ])
    
    # EV Hesaplamaları & 4 Tahmin Mantığı
    ev_dict = {
        "MS 1": {"prob": ms.get('MS 1', 0), "oran": ms1_oran, "ev": beklenen_deger_hesapla(ms1_oran, ms.get('MS 1', 0))},
        "MS 0": {"prob": ms.get('MS 0', 0), "oran": ms0_oran, "ev": beklenen_deger_hesapla(ms0_oran, ms.get('MS 0', 0))},
        "MS 2": {"prob": ms.get('MS 2', 0), "oran": ms2_oran, "ev": beklenen_deger_hesapla(ms2_oran, ms.get('MS 2', 0))},
        "2.5 ÜST": {"prob": ust, "oran": ust_oran, "ev": beklenen_deger_hesapla(ust_oran, ust)},
        "KG VAR": {"prob": kg, "oran": kg_oran, "ev": beklenen_deger_hesapla(kg_oran, kg)}
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

    with tab1:
        st.subheader("Piyasa Beklentisi vs. Gerçekleşenler")
        grafik_verisi = pd.DataFrame({"Sonuç": ["MS 1", "MS 0", "MS 2"], "Gerçekleşen (%)": [ms.get('MS 1', 0), ms.get('MS 0', 0), ms.get('MS 2', 0)]}).set_index("Sonuç")
        st.bar_chart(grafik_verisi, color="#1f77b4")
        
        st.markdown("---")
        st.subheader("🔍 İnteraktif Benzer Maçlar Veritabanı")
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1: gosterilecek_sayi = st.slider("Gösterilecek Maç Sayısı", min_value=5, max_value=50, value=10, step=5)
        with col_f2: ms_filtre = st.multiselect("Sonuca Göre Filtrele", options=["MS 1", "MS 0", "MS 2"], default=["MS 1", "MS 0", "MS 2"])
        with col_f3: 
            tum_iy_ms = ["1/1", "1/0", "1/2", "0/1", "0/0", "0/2", "2/1", "2/0", "2/2"]
            iy_ms_filtre = st.multiselect("İY/MS Senaryosuna Göre Filtrele", options=tum_iy_ms, default=tum_iy_ms)
        
        filtreli_df = st.session_state['benzer_maclar'][
            (st.session_state['benzer_maclar']['Sonuç'].isin(ms_filtre)) & 
            (st.session_state['benzer_maclar']['İY/MS'].isin(iy_ms_filtre))
        ]
        st.dataframe(filtreli_df.head(gosterilecek_sayi))

    with tab2:
        st.subheader("Geçmiş Performans Testi (Backtest)")
        iy_ms_df = pd.DataFrame(list(iy_ms.items()), columns=['İY/MS Senaryosu', 'Gerçekleşme (%)']).sort_values(by='Gerçekleşme (%)', ascending=False).reset_index(drop=True)
        st.dataframe(iy_ms_df)
        
        st.markdown("### 💎 Ekstrem Bahis İhtimalleri")
        ek1, ek2 = st.columns(2)
        fark_15 = round(st.session_state['iki_yari_15_ust'] - 6.0, 1)
        fark_kg = round(st.session_state['iki_yari_kg'] - 3.0, 1)
        ek1.metric("İki Yarıda 1.5 Üst", f"%{st.session_state['iki_yari_15_ust']}", f"Ortalamadan %{abs(fark_15)} {'Yüksek' if fark_15 > 0 else 'Düşük'}", "normal" if fark_15 > 0 else "inverse")
        ek2.metric("İki Yarıda KG Var", f"%{st.session_state['iki_yari_kg']}", f"Ortalamadan %{abs(fark_kg)} {'Yüksek' if fark_kg > 0 else 'Düşük'}", "normal" if fark_kg > 0 else "inverse")

    with tab3:
        st.subheader("💰 Finansal Analiz (Değerli Bahis)")
        if en_degerli_ev > 0:
            st.success(f"💎 **VALUE BET BULUNDU:** Bahis şirketinin hatası **{en_degerli_isim}** oranında yakalandı (+{en_degerli_ev} TL EV).")
        else:
            st.error("⚠️ **RİSKLİ MAÇ:** Standart oranlar kâr marjını yenemiyor.")

        st.markdown("---")
        st.subheader("🧠 Ajanın 4 Aşamalı Stratejisi")
        st.write(f"Saha İçi İstatistikleri: **İY Gol:** {stats['iy_gol']} | **2.Yarı Gol:** {stats['ikinci_yari_gol']} | **Korner:** {stats['korner']} | **Şut:** {stats['sut']}")

        c_t1, c_t2 = st.columns(2)
        c_t3, c_t4 = st.columns(2)

        c_t1.info(f"🛡️ **BANKO TAHMİN**\n\n**{banko_isim}** (Oran: {banko_oran})")
        c_t2.success(f"🎯 **İDEAL TAHMİN (Value)**\n\n**{ideal_isim}** (Oran: {ideal_oran})")
        c_t3.warning(f"⏱️ **İY/MS TAHMİNİ**\n\n**{en_yuksek_iyms}** (Oran: {iyms_oran_tahmin})")
        c_t4.error(f"🧨 **SÜRPRİZ (Longshot)**\n\n**{surpriz_isim}** (Oran: {surpriz_oran})")

        st.markdown("---")
        # 📌 TAKİBE AL BUTONU (Tıklandığında dosyaya kaydeder)
        if st.button("📌 Bu Analizi ve 4 Tahmini Takibe Al (Sisteme Kaydet)", use_container_width=True):
            df_takip = takip_dosyasi_yukle()
            yeni_id = len(df_takip) + 1
            yeni_kayit = {
                'ID': yeni_id,
                'Tarih': pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
                'Mac': aktif_mac,
                'Banko_Tahmin': banko_isim, 'Banko_Oran': banko_oran,
                'Ideal_Tahmin': ideal_isim, 'Ideal_Oran': ideal_oran,
                'IYMS_Tahmin': en_yuksek_iyms, 'IYMS_Oran': iyms_oran_tahmin,
                'Surpriz_Tahmin': surpriz_isim, 'Surpriz_Oran': surpriz_oran,
                'IY_Skor': 'Oynanmadı', 'MS_Skor': 'Oynanmadı', 'Durum': 'Bekliyor'
            }
            df_takip = pd.concat([df_takip, pd.DataFrame([yeni_kayit])], ignore_index=True)
            takip_dosyasi_kaydet(df_takip)
            st.toast("✅ Maç ve 4 Tahmin Başarıyla Takibe Alındı! 'Tahmin Takibi' Sekmesinden İnceleyebilirsiniz.", icon="📌")

   # 4. SEKME: TAHMİN TAKİBİ & ÖĞRENEN SİSTEM KARNESİ
    with tab4:
        st.subheader("📈 Takibe Alınan Maçlar & İsabet Oranı Karnesi")
        df_takip = takip_dosyasi_yukle()
        
        if len(df_takip) == 0:
            st.info("Henüz takibe alınmış bir maç yok. 'ROI & Kasa Yönetimi' sekmesinden analiz ettiğiniz maçları takibe alabilirsiniz.")
        else:
            # --- 1. OTOMATİK GÜNCELLEME SİMÜLASYONU VE API ALTYAPISI ---
            bekleyen_sayisi = len(df_takip[df_takip['Durum'] == 'Bekliyor'])
            col_btn, col_info = st.columns([1, 2])
            
            with col_btn:
                if st.button(f"🔄 Bekleyen {bekleyen_sayisi} Maçın Skorunu Otomatik Çek", use_container_width=True):
                    with st.spinner("İnternette maç sonuçları aranıyor... (Not: Detaylı korner/kart istatistikleri için ileride resmi bir API entegre edilmelidir)"):
                        # BURASI İLERİDE API BAĞLANACAK YERDİR. Şimdilik kullanıcıya bilgi verir.
                        st.warning("⚠️ Otomatik sonuç çekme altyapısı hazır! Ancak kesintisiz çalışması için ileride bir 'Football API' (Örn: API-Sports) entegre etmeliyiz. Şimdilik skorları aşağıdan onaylayarak sisteme öğretebilirsin.")
            
            st.markdown("---")
            
            # --- 2. BAŞARI ORANI HESAPLAMA MOTORU (Doğru/Yanlış Mantığı) ---
            tamamlananlar = df_takip[df_takip['Durum'] == 'Tamamlandı'].copy()
            
            b_hit, b_miss = 0, 0
            i_hit, i_miss = 0, 0
            iyms_hit, iyms_miss = 0, 0
            s_hit, s_miss = 0, 0
            toplam_t = len(tamamlananlar)
            
            if toplam_t > 0:
                for idx, row in tamamlananlar.iterrows():
                    iy_h, iy_a = map(int, row['IY_Skor'].split('-'))
                    ms_h, ms_a = map(int, row['MS_Skor'].split('-'))
                    
                    # Gerçekleşen Sonuçların Tespiti
                    ms_res = "MS 1" if ms_h > ms_a else ("MS 2" if ms_a > ms_h else "MS 0")
                    kg_res = "KG VAR" if (ms_h > 0 and ms_a > 0) else "KG YOK"
                    ust_res = "2.5 ÜST" if (ms_h + ms_a) > 2.5 else "2.5 ALT"
                    iy_res = "1" if iy_h > iy_a else ("2" if iy_a > iy_h else "0")
                    ms_kisa = "1" if ms_h > ms_a else ("2" if ms_a > ms_h else "0")
                    iyms_res = f"{iy_res}/{ms_kisa}"
                    
                    # Banko Kontrol
                    if row['Banko_Tahmin'] in [ms_res, kg_res, ust_res]: b_hit += 1
                    else: b_miss += 1
                        
                    # İdeal Kontrol
                    if row['Ideal_Tahmin'] in [ms_res, kg_res, ust_res]: i_hit += 1
                    elif row['Ideal_Tahmin'] != "Pas Geç": i_miss += 1
                        
                    # İY/MS Kontrol
                    if row['IYMS_Tahmin'] == iyms_res: iyms_hit += 1
                    else: iyms_miss += 1
                        
                    # Sürpriz Kontrol
                    if row['Surpriz_Tahmin'] in [ms_res, iyms_res, "İki Yarı 1.5 Üst"]: s_hit += 1
                    else: s_miss += 1

                st.markdown("### 🎯 Ajanın Canlı İsabet Karnesi")
                m1, m2, m3, m4 = st.columns(4)
                
                m1.metric(
                    "Banko Başarı Oranı", 
                    f"%{round((b_hit/toplam_t)*100, 1)}", 
                    f"✅ {b_hit} Doğru | ❌ {b_miss} Yanlış"
                )
                
                i_toplam = i_hit + i_miss
                if i_toplam > 0:
                    m2.metric(
                        "İdeal (Value) Başarısı", 
                        f"%{round((i_hit/i_toplam)*100, 1)}", 
                        f"✅ {i_hit} Doğru | ❌ {i_miss} Yanlış"
                    )
                else:
                    m2.metric("İdeal (Value) Başarısı", "%0", "Veri Yok")
                    
                m3.metric(
                    "İY/MS İsabeti", 
                    f"%{round((iyms_hit/toplam_t)*100, 1)}", 
                    f"✅ {iyms_hit} Doğru | ❌ {iyms_miss} Yanlış"
                )
                
                m4.metric(
                    "Sürpriz İsabeti", 
                    f"%{round((s_hit/toplam_t)*100, 1)}", 
                    f"✅ {s_hit} Doğru | ❌ {s_miss} Yanlış"
                )
                st.markdown("---")

            # --- 3. MAÇ LİSTESİ VE MANUEL ONAY ALANI ---
            st.markdown("### 📝 Kayıtlı Maçlar Listesi")
            
            # Tabloyu daha şık göstermek için renklendirme fonksiyonu
            def highlight_status(val):
                color = '#1f77b4' if val == 'Bekliyor' else '#2ca02c'
                return f'color: {color}; font-weight: bold'
                
            st.dataframe(df_takip.style.map(highlight_status, subset=['Durum']), use_container_width=True)
            
            st.markdown("#### ⚽ Biten Maçın Skorunu Sisteme Öğret")
            bekleyenler = df_takip[df_takip['Durum'] == 'Bekliyor']
            if len(bekleyenler) > 0:
                c_s1, c_s2, c_s3, c_s4 = st.columns([2, 1, 1, 1])
                secili_id = c_s1.selectbox("Maç Seç:", bekleyenler['ID'].tolist(), format_func=lambda x: f"ID {x}: {df_takip.loc[df_takip['ID']==x, 'Mac'].values[0]}")
                iy_skor_gir = c_s2.text_input("İlk Yarı Skoru (Örn: 1-0):", value="0-0")
                ms_skor_gir = c_s3.text_input("Maç Sonu Skoru (Örn: 2-1):", value="0-0")
                
                # Butonu hizalamak için boşluk ekliyoruz
                c_s4.markdown("<br>", unsafe_allow_html=True) 
                if c_s4.button("💾 Skoru Onayla"):
                    df_takip.loc[df_takip['ID'] == secili_id, 'IY_Skor'] = iy_skor_gir
                    df_takip.loc[df_takip['ID'] == secili_id, 'MS_Skor'] = ms_skor_gir
                    df_takip.loc[df_takip['ID'] == secili_id, 'Durum'] = 'Tamamlandı'
                    takip_dosyasi_kaydet(df_takip)
                    st.success("Skor başarıyla güncellendi! Ajan bu sonuçtan ders çıkardı ve karnesi güncellendi.")
                    st.rerun()
            else:
                st.info("🎉 Bekleyen maçınız yok. Tüm tahminler sonuçlandırılmış ve yapay zekanın karnesine işlenmiş!")
