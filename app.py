import streamlit as st
import pandas as pd
import numpy as np
from sklearn.neighbors import NearestNeighbors
import requests
from bs4 import BeautifulSoup
import warnings
warnings.filterwarnings('ignore')

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="MacApp Pro", page_icon="⚽", layout="wide")

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
    
    # 2. Kusursuz Temizlik
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
    
    # Detaylı Saha İçi İstatistikleri (Korner, Şut, Gol Dağılımı)
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
    
    tab1, tab2, tab3 = st.tabs(["📊 Görsel Dashboard", "🧪 Backtest", "💰 ROI & Kasa Yönetimi (Yapay Zeka Yorumu)"])
    
    with tab1:
        st.subheader("Piyasa Beklentisi vs. Gerçekleşenler")
        
        grafik_verisi = pd.DataFrame({
            "Sonuç": ["MS 1", "MS 0 (Beraberlik)", "MS 2"],
            "Geçmişte Gerçekleşen (%)": [ms.get('MS 1', 0), ms.get('MS 0', 0), ms.get('MS 2', 0)]
        }).set_index("Sonuç")
        
        col_grafik1, col_grafik2 = st.columns(2)
        with col_grafik1:
            st.markdown("**Maç Sonucu Dağılımı**")
            st.bar_chart(grafik_verisi, color="#1f77b4")
            
        with col_grafik2:
            st.markdown("**Gol Beklentisi Göstergesi**")
            st.progress(kg / 100, text=f"KG Var İhtimali: %{kg}")
            st.progress(ust / 100, text=f"2.5 Üst İhtimali: %{ust}")
            
        st.markdown("---")
        st.subheader("🔍 İnteraktif Benzer Maçlar Veritabanı (50 Örneklem)")
        
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            gosterilecek_sayi = st.slider("Gösterilecek Maç Sayısı", min_value=5, max_value=50, value=10, step=5)
        with col_f2:
            ms_filtre = st.multiselect("Sonuca Göre Filtrele", options=["MS 1", "MS 0", "MS 2"], default=["MS 1", "MS 0", "MS 2"])
        with col_f3:
            tum_iy_ms = ["1/1", "1/0", "1/2", "0/1", "0/0", "0/2", "2/1", "2/0", "2/2"]
            iy_ms_filtre = st.multiselect("İY/MS Senaryosuna Göre Filtrele", options=tum_iy_ms, default=tum_iy_ms)
        
        filtreli_df = st.session_state['benzer_maclar'][
            (st.session_state['benzer_maclar']['Sonuç'].isin(ms_filtre)) & 
            (st.session_state['benzer_maclar']['İY/MS'].isin(iy_ms_filtre))
        ]
        
        st.dataframe(filtreli_df.head(gosterilecek_sayi))
        
        csv_data = filtreli_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 Bu 50 Benzer Maçın Verisini Excel (CSV) Olarak İndir",
            data=csv_data,
            file_name="macapp_benzer_maclar_analizi.csv",
            mime="text/csv"
        )
    with tab2:
        st.subheader("Geçmiş Performans Testi (Backtest)")
        iy_ms_df = pd.DataFrame(list(iy_ms.items()), columns=['İY/MS Senaryosu', 'Gerçekleşme (%)']).sort_values(by='Gerçekleşme (%)', ascending=False).reset_index(drop=True)
        st.dataframe(iy_ms_df)
        
        st.markdown("### 💎 Ekstrem Bahis İhtimalleri")
        st.info("💡 Dünya genelinde 'İki Yarıda 1.5 Üst' %6, 'İki Yarı KG' ise %3 ihtimalle gelir. Oklar, maçın potansiyelini gösterir.")
        ek1, ek2 = st.columns(2)
        fark_15 = round(st.session_state['iki_yari_15_ust'] - 6.0, 1)
        fark_kg = round(st.session_state['iki_yari_kg'] - 3.0, 1)
        ek1.metric("İki Yarıda 1.5 Üst", f"%{st.session_state['iki_yari_15_ust']}", f"Ortalamadan %{abs(fark_15)} {'Yüksek' if fark_15 > 0 else 'Düşük'}", "normal" if fark_15 > 0 else "inverse")
        ek2.metric("İki Yarıda KG Var", f"%{st.session_state['iki_yari_kg']}", f"Ortalamadan %{abs(fark_kg)} {'Yüksek' if fark_kg > 0 else 'Düşük'}", "normal" if fark_kg > 0 else "inverse")

    with tab3:
        st.subheader("💰 Finansal Analiz (Değerli Bahis)")
        
        # EV (Expected Value) Hesaplamaları
        ev_dict = {
            "MS 1": {"prob": ms.get('MS 1', 0), "oran": ms1_oran, "ev": beklenen_deger_hesapla(ms1_oran, ms.get('MS 1', 0))},
            "MS 0 (Beraberlik)": {"prob": ms.get('MS 0', 0), "oran": ms0_oran, "ev": beklenen_deger_hesapla(ms0_oran, ms.get('MS 0', 0))},
            "MS 2": {"prob": ms.get('MS 2', 0), "oran": ms2_oran, "ev": beklenen_deger_hesapla(ms2_oran, ms.get('MS 2', 0))},
            "2.5 ÜST": {"prob": ust, "oran": ust_oran, "ev": beklenen_deger_hesapla(ust_oran, ust)},
            "KG VAR": {"prob": kg, "oran": kg_oran, "ev": beklenen_deger_hesapla(kg_oran, kg)}
        }
        
        en_degerli_isim = max(ev_dict, key=lambda x: ev_dict[x]['ev'])
        en_degerli_ev = ev_dict[en_degerli_isim]['ev']
        
        if en_degerli_ev > 0:
            st.success(f"💎 **VALUE BET BULUNDU:** Bahis şirketinin hatası **{en_degerli_isim}** oranında yakalandı. Her 1 TL yatırıma uzun vadede ortalama +{en_degerli_ev} TL kâr bırakır.")
        else:
            st.error("⚠️ **RİSKLİ MAÇ:** Bu maçtaki hiçbir standart oran İddaa'nın kâr marjını yenemiyor. Banko arayanlar pas geçmeli.")

        st.markdown("---")
        st.subheader("🧠 Ajanın Saha İçi Dinamik Yorumu")
        st.write(f"Sistem geçmiş 50 benzer maçı taradı. İstatistiklere göre bu takımların maçlarında **ilk yarı ortalama {stats['iy_gol']} gol**, **ikinci yarı ise {stats['ikinci_yari_gol']} gol** atılıyor. Toplam maç başı **korner ortalaması {stats['korner']}** ve **şut ortalaması {stats['sut']}** olarak gerçekleşti. Yapay zekanın bu sert istatistiklere dayanarak çıkardığı 4 aşamalı strateji:")

        # 4 Aşamalı Tahmin Algoritması
        banko_isim = max(ev_dict, key=lambda x: ev_dict[x]['prob'])
        banko_oran = ev_dict[banko_isim]['oran']
        
        ideal_isim = en_degerli_isim if en_degerli_ev > 0 else "Değerli Oran Yok (Pas Geçiniz)"
        ideal_oran = ev_dict[en_degerli_isim]['oran'] if en_degerli_ev > 0 else "-"
        
        en_yuksek_iyms = max(iy_ms, key=iy_ms.get)
        iyms_oran_tahmin = round((100 / (iy_ms[en_yuksek_iyms] if iy_ms[en_yuksek_iyms] > 0 else 1.1)) * 0.85, 2)
        
        ters_iyms = {k: v for k, v in iy_ms.items() if k in ['1/2', '2/1'] and v > 0}
        if ters_iyms:
            surpriz_isim = max(ters_iyms, key=ters_iyms.get) + " (İY/MS Dönüşü)"
            surpriz_oran = round((100 / ters_iyms[surpriz_isim[:3]]) * 0.85, 2)
        elif st.session_state['iki_yari_15_ust'] > 8:
            surpriz_isim = "Her İki Yarıda 1.5 Üst"
            surpriz_oran = round((100 / st.session_state['iki_yari_15_ust']) * 0.85, 2)
        else:
            surpriz_isim = "Maç Sonu Beraberlik"
            surpriz_oran = ms0_oran

        c_t1, c_t2 = st.columns(2)
        c_t3, c_t4 = st.columns(2)

        c_t1.info(f"🛡️ **BANKO TAHMİN**\n\n**{banko_isim}**\n\nOran: **{banko_oran}** (Olasılık: %{ev_dict[banko_isim]['prob']})")
        c_t2.success(f"🎯 **İDEAL TAHMİN (Value)**\n\n**{ideal_isim}**\n\nOran: **{ideal_oran}** (Matematiksel Fırsat)")
        c_t3.warning(f"⏱️ **İY/MS TAHMİNİ**\n\n**{en_yuksek_iyms}**\n\nTahmini Oran: **{iyms_oran_tahmin}** (Gerçekleşme: %{iy_ms[en_yuksek_iyms]})")
        c_t4.error(f"🧨 **SÜRPRİZ (Longshot)**\n\n**{surpriz_isim}**\n\nTahmini Oran: **{surpriz_oran}** (Yüksek Kazanç Potansiyeli)")
