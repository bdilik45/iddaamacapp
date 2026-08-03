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

# --- YAPAY ZEKA MOTORU (YENİ VERİ SETİNE UYUMLANDI) ---
@st.cache_resource
def motoru_baslat():
    # DOSYA ADINI BURAYA YAZIYORUZ (.csv, .zip veya .parquet hangisini kullanıyorsan uzantıya dikkat et)
    veri_yolu = "iddaa_arsiv_YEDEK.parquet" 
    df = pd.read_parquet(veri_yolu, low_memory=False)
    
    # 1. YENİ BAŞLIKLARI BİZİM SİSTEME TERCÜME EDİYORUZ
    df['Mac'] = df['HomeTeam'] + " - " + df['AwayTeam']
    df['res'] = df['FTR']  # FTR: Full Time Result (H, D, A)
    df['tot'] = df['FTHG'] + df['FTAG']  # Toplam Gol
    
    df['Open_H'] = df['B365H']
    df['Open_D'] = df['B365D']
    df['Open_A'] = df['B365A']
    df['Open_O25'] = df['B365>2.5']
    
    # 2. HAM ORANLARDAN SAF OLASILIKLARI YZ İÇİN OTOMATİK HESAPLIYORUZ
    # Taraf Bahsi Marjı
    margin = (1 / df['Open_H']) + (1 / df['Open_D']) + (1 / df['Open_A'])
    df['pH'] = (1 / df['Open_H']) / margin
    df['pD'] = (1 / df['Open_D']) / margin
    df['pA'] = (1 / df['Open_A']) / margin
    
    # Alt/Üst Marjı
    margin_ou = (1 / df['B365>2.5']) + (1 / df['B365<2.5'])
    df['pOver'] = (1 / df['B365>2.5']) / margin_ou
    
    # 3. EKSİK VERİLERİ (Açılmamış Oranları) TEMİZLİYORUZ
    df = df.dropna(subset=['pH', 'pD', 'pA', 'pOver', 'FTHG', 'FTAG', 'HTHG', 'HTAG', 'Open_H', 'Open_D', 'Open_A', 'Open_O25', 'res'])
    
    # Not: Yeni veride KG Var açılış oranı standart olmadığı için YZ modeli KG'ye değil 4 ana faktöre odaklanacak.
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
    
    hedef_maclar['IY_Kod'] = np.where(hedef_maclar['HTHG'] > hedef_maclar['HTAG'], '1', 
                             np.where(hedef_maclar['HTHG'] < hedef_maclar['HTAG'], '2', '0'))
    
    ms_kisa_map = {'H': '1', 'D': '0', 'A': '2'}
    hedef_maclar['MS_Kisa'] = hedef_maclar['res'].map(ms_kisa_map)
    hedef_maclar['IY_MS'] = hedef_maclar['IY_Kod'] + "/" + hedef_maclar['MS_Kisa']
    
    tum_ihtimaller = {
        '1/1': 0.0, '1/0': 0.0, '1/2': 0.0, 
        '0/1': 0.0, '0/0': 0.0, '0/2': 0.0, 
        '2/1': 0.0, '2/0': 0.0, '2/2': 0.0
    }
    hesaplanan_oranlar = (hedef_maclar['IY_MS'].value_counts(normalize=True) * 100).round(1).to_dict()
    tum_ihtimaller.update(hesaplanan_oranlar)
    iy_ms_oranlari = tum_ihtimaller
    
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
    
    tablo_df = tablo_df.rename(columns={
        'Date': 'Tarih',
        'Mac': 'Maç',
        'Open_H': 'Oran 1',
        'Open_D': 'Oran X',
        'Open_A': 'Oran 2',
        'Open_O25': 'Oran Üst',
        'MS_Kod': 'Sonuç',
        'IY_MS': 'İY/MS'
    })[['Tarih', 'Maç', 'Oran 1', 'Oran X', 'Oran 2', 'Oran Üst', 'İlk Yarı Skoru', 'Maç Sonu Skoru', 'Sonuç', 'İY/MS']]

    return ms_oranlari, kg_yuzdesi, ust_yuzdesi, yildizlar, tablo_df, iy_ms_oranlari

def beklenen_deger_hesapla(oran, ihtimal_yuzdesi):
    ihtimal = ihtimal_yuzdesi / 100
    ev = (ihtimal * oran) - 1
    return round(ev, 3)

# --- MACKOLİK WEB SCRAPING MOTORU ---
@st.cache_data(ttl=1800)
def bulteni_kazi():
    cekilen_maclar = {"Manuel Giriş (Kendim Yazacağım)": {"ms1": 1.92, "ms0": 3.01, "ms2": 2.86, "ust": 1.60, "kg": 1.48}}
    
    url = "https://arsiv.mackolik.com/Iddaa-Programi"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'tr-TR,tr;q=0.8,en-US;q=0.5,en;q=0.3'
    }
    
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
                    
                    if ms1 == 1.01 and ms0 == 1.01: 
                        continue
                    
                    takim_adi = "Bilinmeyen Maç"
                    tds = row.find_all('td')
                    for td in tds:
                        if " - " in td.text and len(td.text.strip()) > 5:
                            takim_adi = " ".join(td.text.strip().split())
                            break
                    
                    cekilen_maclar[takim_adi] = {"ms1": ms1, "ms0": ms0, "ms2": ms2, "ust": ust, "kg": kg}
                    basarili_veri += 1
                except Exception:
                    continue
                    
        if basarili_veri == 0:
            raise ValueError("Mackolik etiketleri bulunamadı veya bülten boş.")
            
    except Exception as e:
        st.sidebar.warning(f"⚠️ Mackolik'ten şu an canlı veri çekilemedi. Yedek bülten devrede.")
        cekilen_maclar.update({
            "🔴 (Yedek) Galatasaray - Fenerbahçe": {"ms1": 2.10, "ms0": 3.20, "ms2": 2.60, "ust": 1.75, "kg": 1.55}
        })
        
    return cekilen_maclar

# --- WEB ARAYÜZÜ (UI) ---
st.title("⚽ MacApp Pro | Analiz & Yatırım Terminali")
st.markdown(f"*(**{len(df)}** maçlık devasa makine öğrenmesi veritabanı aktif)*")

st.sidebar.header("🌐 Canlı Bülten (Mackolik)")
guncel_bulten = bulteni_kazi()

secilen_mac = st.sidebar.selectbox("Analiz Edilecek Maçı Seçin:", list(guncel_bulten.keys()))
secili_oranlar = guncel_bulten[secilen_mac]

st.sidebar.markdown("---")
st.sidebar.header("Maç Oranları")

st.sidebar.info("💡 **Not:** KG Var oranı sitede gizli sekmede olduğu için varsayılan (1.50) atanmıştır. İsterseniz analizden önce aşağıdan elinizle düzeltebilirsiniz.")

ms1_oran = st.sidebar.number_input("MS 1 Oranı", min_value=1.01, value=float(secili_oranlar["ms1"]), step=0.05)
ms0_oran = st.sidebar.number_input("MS X (Beraberlik)", min_value=1.01, value=float(secili_oranlar["ms0"]), step=0.05)
ms2_oran = st.sidebar.number_input("MS 2 Oranı", min_value=1.01, value=float(secili_oranlar["ms2"]), step=0.05)
st.sidebar.markdown("---")
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

if st.sidebar.button("🔍 Yapay Zeka Analizini Başlat", use_container_width=True):
    with st.spinner("MacApp geçmiş verileri tarıyor ve simülasyonları çalıştırıyor..."):
        # YZ artık 4 boyutlu vektör kullanıyor (pKG çıkarıldı)
        ms, kg, ust, yildizlar, benzer_maclar, iy_ms = analiz_et(ph_gercek, pd_gercek, pa_gercek, pover_gercek)
        
        st.session_state['analiz_tamam'] = True
        st.session_state['ms'] = ms
        st.session_state['kg'] = kg
        st.session_state['ust'] = ust
        st.session_state['yildizlar'] = yildizlar
        st.session_state['benzer_maclar'] = benzer_maclar
        st.session_state['iy_ms'] = iy_ms
        st.session_state['secilen_mac_baslik'] = secilen_mac

if st.session_state.get('analiz_tamam', False):
    ms = st.session_state['ms']
    kg = st.session_state['kg']
    ust = st.session_state['ust']
    yildizlar = st.session_state['yildizlar']
    benzer_maclar = st.session_state['benzer_maclar']
    iy_ms = st.session_state['iy_ms']
    aktif_mac = st.session_state.get('secilen_mac_baslik', 'Manuel Maç')

    st.success(f"**Şu An Analiz Edilen Maç:** {aktif_mac}")
    st.info("💡 **Ajanın Temizlenmiş Olasılıkları:** Bahis şirketinin kârı çıkarıldığında maçın saf matematiği hesaplandı.")
    if yildizlar:
        for y in yildizlar:
            st.warning(y)
    
    tab1, tab2, tab3 = st.tabs(["📊 Görsel Dashboard", "🧪 Backtest & Başarı Oranı", "💰 ROI & Kasa Yönetimi"])
    
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
        
        filtreli_df = benzer_maclar[
            (benzer_maclar['Sonuç'].isin(ms_filtre)) & 
            (benzer_maclar['İY/MS'].isin(iy_ms_filtre))
        ]
        
        st.dataframe(filtreli_df.head(gosterilecek_sayi), use_container_width=True)
        
        csv_data = filtreli_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 Bu 50 Benzer Maçın Verisini Excel (CSV) Olarak İndir",
            data=csv_data,
            file_name="macapp_benzer_maclar_analizi.csv",
            mime="text/csv"
        )

    with tab2:
        st.subheader("Geçmiş Performans Testi (Backtest)")
        st.write(f"Sisteme girdiğiniz oranlarla birebir aynı oranlara sahip geçmişteki **50 maç** taranmıştır. Ajanın o maçlardaki başarı yüzdeleri:")
        
        en_yuksek_ms = max(ms, key=ms.get) if ms else "Yok"
        
        c1, c2, c3 = st.columns(3)
        c1.metric(label="En Güçlü MS Tahmini", value=en_yuksek_ms, delta=f"Tarihsel Başarı: %{ms.get(en_yuksek_ms, 0)}")
        c2.metric(label="KG Var Güven Skoru", value=f"%{kg}", delta="İdeal eşik: %60" if kg >= 60 else "-Riskli Bölge", delta_color="normal" if kg>=60 else "inverse")
        c3.metric(label="Üst Güven Skoru", value=f"%{ust}", delta="İdeal eşik: %60" if ust >= 60 else "-Riskli Bölge", delta_color="normal" if ust>=60 else "inverse")
        
        st.markdown("### İlk Yarı / Maç Sonucu Dağılımı (Türkçe İddaa Kodları)")
        
        iy_ms_df = pd.DataFrame(list(iy_ms.items()), columns=['İY/MS Senaryosu', 'Geçmişte Görülme Yüzdesi (%)'])
        iy_ms_df = iy_ms_df.sort_values(by='Geçmişte Görülme Yüzdesi (%)', ascending=False).reset_index(drop=True)
        st.dataframe(iy_ms_df, use_container_width=True)

    with tab3:
        st.subheader("Finansal Değer Analizi (Value Bet)")
        st.write("Bu sekme, ajanın bulduğu geçmiş gerçekleşme yüzdeleri ile bahis şirketinin verdiği oranları kıyaslar. **'Beklenen Değer (EV)' 0'dan büyükse**, matematiksel olarak avantajlısınız demektir.")
        
        ev_ms1 = beklenen_deger_hesapla(ms1_oran, ms.get('MS 1', 0))
        ev_ms0 = beklenen_deger_hesapla(ms0_oran, ms.get('MS 0', 0))
        ev_ms2 = beklenen_deger_hesapla(ms2_oran, ms.get('MS 2', 0))
        ev_ust = beklenen_deger_hesapla(ust_oran, ust)
        ev_kg = beklenen_deger_hesapla(kg_oran, kg)
        
        senaryolar = {
            "MS 1": ev_ms1, "MS 0 (Beraberlik)": ev_ms0, "MS 2": ev_ms2, 
            "2.5 ÜST": ev_ust, "KG VAR": ev_kg
        }
        en_degerli_isim = max(senaryolar, key=senaryolar.get)
        en_degerli_ev = senaryolar[en_degerli_isim]
        
        if en_degerli_ev > 0:
            st.success(f"💎 **FIRSAT BULUNDU:** Matematiksel olarak en kârlı tercih **{en_degerli_isim}**. Uzun vadede yatırdığınız her 1 TL için ortalama {en_degerli_ev} TL kâr bırakır.")
        else:
            st.error("⚠️ **RİSKLİ MAÇ:** Bu maçtaki hiçbir oran şirket kâr marjını yenemiyor. Matematiksel olarak bahis yapmaya uygun değil.")
            
        st.markdown("### Yatırım Simülasyonu")
        st.write(f"**Güncel Kasa:** {bakiye} TL | **Risk Edilen:** {bahis_miktari} TL")
        
        if en_degerli_ev > 0:
            beklenen_kar = bahis_miktari * en_degerli_ev
            st.metric(label=f"{en_degerli_isim} Seçimine Oynanırsa Uzun Vadeli Beklenen Net Kâr", value=f"+{round(beklenen_kar, 2)} TL")
        else:
            st.metric(label="Bu Maça Oynamanın Uzun Vadeli Matematiksel Zararı", value="Eksi Yönde (Zarar)")
