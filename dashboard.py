"""
MacApp Pro — Ana Dashboard
===========================
app.py'nin en başında çağrılır. Tek sayfada:
  - Sistem durumu (zamanlayıcı, API kota)
  - Bugünün en iyi önerileri (banko / ideal / surpriz)
  - Tüm bülten maç listesi (durum renkleriyle)
  - Başarı karnesi (market bazlı bar grafik)
"""

import streamlit as st
import pandas as pd
from datetime import datetime

try:
    import scheduler as sched_mod
    import live_scores
    MODULLER_YUKLU = True
except ImportError:
    MODULLER_YUKLU = False


# ── Renkler ve etiketler ──────────────────────────────────────────────────────

def _durum_badge(durum: str) -> str:
    if durum == "Tamamlandı":
        return "🟢"
    elif durum == "Bekliyor":
        return "🟡"
    else:
        return "⚪"


def _isabet_renk(oran: float) -> str:
    if oran >= 70:
        return "normal"
    elif oran >= 55:
        return "off"
    else:
        return "inverse"


# ── Dashboard ana fonksiyonu ──────────────────────────────────────────────────

def goster(takip_dosyasi_yukle, radar_dosyasi_yukle, bulteni_kazi):
    """
    app.py'den çağrılır:
        import dashboard
        dashboard.goster(takip_dosyasi_yukle, radar_dosyasi_yukle, bulteni_kazi)
    """

    bugun = datetime.now().strftime("%Y-%m-%d")
    simdi = datetime.now().strftime("%H:%M")

    # ── Başlık ───────────────────────────────────────────────────────────────
    col_bas, col_sag = st.columns([3, 1])
    with col_bas:
        st.markdown(f"## ⚽ MacApp Pro — Günlük Kontrol Paneli")
        st.caption(f"{datetime.now().strftime('%A, %d %B %Y')} · Güncelleme: {simdi}")
    with col_sag:
        if st.button("🔄 Yenile", use_container_width=True):
            st.rerun()

    st.divider()

    # ── Sistem durumu kartları ────────────────────────────────────────────────
    with st.container():
        c1, c2, c3, c4 = st.columns(4)

        # Zamanlayıcı durumu
        if MODULLER_YUKLU:
            durum = sched_mod.zamanlayici_durumu()
            zam_durum = "🟢 Çalışıyor" if durum["aktif"] else "🔴 Durdu"
            bugun_analiz = durum.get("bugun_analiz", 0)
            toplam_analiz = durum.get("toplam_analiz", 0)

            son_tarama = durum.get("son_tarama")
            if son_tarama:
                son_dt = pd.to_datetime(son_tarama)
                son_str = son_dt.strftime("%d/%m %H:%M")
            else:
                son_str = "Henüz yok"

            son_skor = durum.get("son_canli_skor")
            if son_skor:
                skor_dt = pd.to_datetime(son_skor)
                skor_str = skor_dt.strftime("%H:%M")
            else:
                skor_str = "—"

            # API kotası
            try:
                kota = live_scores.api_kota_kontrol()
                kota_str = f"{kota['kullanilan']}/{kota['limit']}"
            except Exception:
                kota_str = "—"
        else:
            zam_durum = "⚠️ Modül yok"
            bugun_analiz = 0
            toplam_analiz = 0
            son_str = "—"
            skor_str = "—"
            kota_str = "—"

        c1.metric("Zamanlayıcı", zam_durum, f"Son tarama: {son_str}")
        c2.metric("Bugün analiz", f"{bugun_analiz} maç", f"Toplam: {toplam_analiz}")
        c3.metric("Canlı skor", f"Son: {skor_str}", "Her 30 dakika")
        c4.metric("API kota", kota_str, "istek / gün")

    st.divider()

    # ── Veri yükleme ──────────────────────────────────────────────────────────
    df_radar = radar_dosyasi_yukle()
    df_takip = takip_dosyasi_yukle()

    bugun_radar = df_radar[df_radar["Tarih"] == bugun].copy() if len(df_radar) > 0 else pd.DataFrame()

    # ── BÖLÜM 1: Bugünün önerileri ───────────────────────────────────────────
    st.subheader("🎯 Bugünün Önerileri")

    if len(df_takip) > 0:
        bugun_takip = df_takip[df_takip["Tarih"] == bugun].copy() if "Tarih" in df_takip.columns else pd.DataFrame()
    else:
        bugun_takip = pd.DataFrame()

    if len(bugun_takip) > 0:
        for _, satir in bugun_takip.iterrows():
            durum = str(satir.get("Durum", "Bekliyor"))
            mac = str(satir.get("Mac", ""))
            badge = _durum_badge(durum)

            with st.container(border=True):
                st.markdown(f"**{badge} {mac}**")
                col_b, col_i, col_s, col_d = st.columns(4)

                banko = str(satir.get("Banko_Tahmin", "—"))
                banko_oran = satir.get("Banko_Oran", "")
                ideal = str(satir.get("Ideal_Tahmin", "—"))
                ideal_oran = satir.get("Ideal_Oran", "")
                surpriz = str(satir.get("Surpriz_Tahmin", "—"))
                surpriz_oran = satir.get("Surpriz_Oran", "")

                col_b.markdown(
                    f"<div style='background:#0f3d2e; padding:10px; border-radius:8px; border-left:3px solid #1D9E75;'>"
                    f"<div style='font-size:11px; color:#6fcfa0;'>🔒 Banko</div>"
                    f"<div style='font-size:16px; font-weight:600; color:#fff;'>{banko}</div>"
                    f"<div style='font-size:11px; color:#6fcfa0;'>oran {banko_oran}</div></div>",
                    unsafe_allow_html=True
                )
                col_i.markdown(
                    f"<div style='background:#0a2d4d; padding:10px; border-radius:8px; border-left:3px solid #378ADD;'>"
                    f"<div style='font-size:11px; color:#6baee8;'>💡 İdeal (value)</div>"
                    f"<div style='font-size:16px; font-weight:600; color:#fff;'>{ideal}</div>"
                    f"<div style='font-size:11px; color:#6baee8;'>oran {ideal_oran}</div></div>",
                    unsafe_allow_html=True
                )
                col_s.markdown(
                    f"<div style='background:#3d2800; padding:10px; border-radius:8px; border-left:3px solid #BA7517;'>"
                    f"<div style='font-size:11px; color:#e0a94a;'>⚡ Surpriz</div>"
                    f"<div style='font-size:16px; font-weight:600; color:#fff;'>{surpriz}</div>"
                    f"<div style='font-size:11px; color:#e0a94a;'>oran {surpriz_oran}</div></div>",
                    unsafe_allow_html=True
                )

                if durum == "Tamamlandı":
                    ms_skor = str(satir.get("MS_Skor", ""))
                    iy_skor = str(satir.get("IY_Skor", ""))
                    sut = str(satir.get("Sut", "—"))
                    korner = str(satir.get("Korner", "—"))
                    kart = str(satir.get("Kart", "—"))
                    col_d.markdown(
                        f"<div style='background:#1a1a2e; padding:10px; border-radius:8px;'>"
                        f"<div style='font-size:11px; color:#aaa;'>Sonuç</div>"
                        f"<div style='font-size:18px; font-weight:600; color:#fff;'>{ms_skor}</div>"
                        f"<div style='font-size:11px; color:#aaa;'>İY: {iy_skor} · ⚽{sut} 🚩{korner} 🟨{kart}</div></div>",
                        unsafe_allow_html=True
                    )
                elif durum == "Bekliyor":
                    col_d.markdown(
                        "<div style='background:#1a1a1a; padding:10px; border-radius:8px; text-align:center;'>"
                        "<div style='font-size:24px;'>⏳</div>"
                        "<div style='font-size:11px; color:#aaa;'>Oynanacak</div></div>",
                        unsafe_allow_html=True
                    )
    else:
        st.info("Bugün henüz kayıtlı tahmin yok. Sağdaki menüden maç analizi yaparak tahmini kaydet.")

    # ── BÖLÜM 2: Tüm bülten listesi ──────────────────────────────────────────
    st.divider()
    st.subheader("📋 Bugünün Bülten Maçları")

    if len(bugun_radar) > 0:
        # Durum sıralama: oynanıyor → bekliyor → tamamlandı
        durum_sira = {"Bekliyor": 0, "Tamamlandı": 1, "Veri Girilmedi": 2}
        bugun_radar["_sira"] = bugun_radar["Durum"].map(durum_sira).fillna(3)
        bugun_radar = bugun_radar.sort_values("_sira").drop(columns=["_sira"])

        bekleyen_sayi = (bugun_radar["Durum"] == "Bekliyor").sum()
        tamamlanan_sayi = (bugun_radar["Durum"] == "Tamamlandı").sum()

        col_istat1, col_istat2, col_istat3 = st.columns(3)
        col_istat1.metric("Toplam maç", len(bugun_radar))
        col_istat2.metric("Bekleyen", bekleyen_sayi)
        col_istat3.metric("Sonuçlanan", tamamlanan_sayi)

        st.dataframe(
            bugun_radar[[
                "Mac", "MS_Tahmin", "KG_Tahmin", "Ust25_Tahmin",
                "IY05_Tahmin", "IY15_Tahmin", "MS_Skor", "IY_Skor", "Durum"
            ]].rename(columns={
                "Mac": "Maç",
                "MS_Tahmin": "MS",
                "KG_Tahmin": "KG",
                "Ust25_Tahmin": "2.5",
                "IY05_Tahmin": "İY 0.5",
                "IY15_Tahmin": "İY 1.5",
                "MS_Skor": "Skor",
                "IY_Skor": "İY Skor",
            }),
            use_container_width=True,
            hide_index=True,
            height=min(400, 50 + len(bugun_radar) * 35),
        )
    else:
        col_bilgi, col_btn = st.columns([3, 1])
        col_bilgi.info("Bugün bülten taraması yapılmamış. Sağ alttaki butona bas veya zamanlayıcı sabah 10:00'da otomatik başlatır.")
        with col_btn:
            if MODULLER_YUKLU and st.button("▶️ Şimdi Tara", use_container_width=True):
                import sys
                scheduler_mod = __import__("scheduler")
                scheduler_mod.manuel_bulten_calistir(sys.modules.get("__main__"))
                st.success("Tarama başladı, 1-2 dk sonra yenile.")

    # ── BÖLÜM 3: Başarı karnesi ───────────────────────────────────────────────
    st.divider()
    st.subheader("📈 Başarı Karnesi")

    tamamlananlar = df_takip[df_takip["Durum"] == "Tamamlandı"].copy() if len(df_takip) > 0 else pd.DataFrame()

    if len(tamamlananlar) == 0:
        st.info("Henüz sonuçlanmış tahmin yok. Maçlar bittikçe karne burada oluşur.")
        return

    karne_veri = _karne_hesapla(tamamlananlar)

    col_k = st.columns(len(karne_veri))
    for i, (market, veri) in enumerate(karne_veri.items()):
        pct = veri["isabet"]
        renk = "#1D9E75" if pct >= 65 else "#BA7517" if pct >= 50 else "#993C1D"
        col_k[i].markdown(
            f"<div style='text-align:center; padding:12px; background:#161b22; border-radius:10px; border:1px solid #30363d;'>"
            f"<div style='font-size:12px; color:#aaa; margin-bottom:4px;'>{market}</div>"
            f"<div style='font-size:26px; font-weight:700; color:{renk};'>%{pct}</div>"
            f"<div style='font-size:11px; color:#aaa;'>{veri['dogru']}✓ / {veri['yanlis']}✗</div>"
            f"</div>",
            unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Bar grafik
    for market, veri in karne_veri.items():
        pct = veri["isabet"]
        renk = "#1D9E75" if pct >= 65 else "#BA7517" if pct >= 50 else "#993C1D"
        st.markdown(
            f"<div style='display:flex; align-items:center; gap:10px; margin-bottom:6px;'>"
            f"<div style='width:100px; font-size:12px; color:#ccc;'>{market}</div>"
            f"<div style='flex:1; background:#21262d; border-radius:99px; height:8px; overflow:hidden;'>"
            f"<div style='width:{pct}%; height:100%; background:{renk}; border-radius:99px;'></div></div>"
            f"<div style='width:36px; font-size:12px; font-weight:600; color:#fff; text-align:right;'>%{pct}</div>"
            f"</div>",
            unsafe_allow_html=True
        )


# ── Karne hesaplama ───────────────────────────────────────────────────────────

def _karne_hesapla(df: pd.DataFrame) -> dict:
    """
    Tamamlanan tahminlerden market bazlı isabet oranı hesaplar.
    Mevcut app.py'deki karne mantığıyla uyumlu.
    """
    karne = {}

    # MS tahmini
    ms_dogru = 0
    ms_yanlis = 0
    for _, satir in df.iterrows():
        tahmin = str(satir.get("Banko_Tahmin", ""))
        skor = str(satir.get("MS_Skor", ""))
        if not tahmin or not skor or skor in ["-", "Oynanmadı", ""]:
            continue
        try:
            ev, dep = map(int, skor.split("-"))
            gercek = "MS 1" if ev > dep else ("MS 2" if dep > ev else "MS X")
            if tahmin.startswith("MS"):
                if gercek == tahmin:
                    ms_dogru += 1
                else:
                    ms_yanlis += 1
        except Exception:
            pass
    if ms_dogru + ms_yanlis > 0:
        karne["MS 1X2"] = {
            "isabet": round(ms_dogru / (ms_dogru + ms_yanlis) * 100, 1),
            "dogru": ms_dogru, "yanlis": ms_yanlis
        }

    # KG tahmini
    if "Ideal_Tahmin" in df.columns:
        kg_dogru = kg_yanlis = 0
        for _, satir in df.iterrows():
            tahmin = str(satir.get("Ideal_Tahmin", ""))
            skor = str(satir.get("MS_Skor", ""))
            if "KG" not in tahmin or not skor or skor in ["-", "Oynanmadı", ""]:
                continue
            try:
                ev, dep = map(int, skor.split("-"))
                gercek_kg = "KG VAR" if ev > 0 and dep > 0 else "KG YOK"
                if "VAR" in tahmin and gercek_kg == "KG VAR":
                    kg_dogru += 1
                elif "YOK" in tahmin and gercek_kg == "KG YOK":
                    kg_dogru += 1
                else:
                    kg_yanlis += 1
            except Exception:
                pass
        if kg_dogru + kg_yanlis > 0:
            karne["KG"] = {
                "isabet": round(kg_dogru / (kg_dogru + kg_yanlis) * 100, 1),
                "dogru": kg_dogru, "yanlis": kg_yanlis
            }

    # Radar bazlı marketler (MS_Skor + IY_Skor üzerinden)
    if "Ust25_Tahmin" in df.columns or "MS_Skor" in df.columns:
        karne.update(_radar_karne(df))

    return karne


def _radar_karne(df: pd.DataFrame) -> dict:
    """Radar tablosu verisiyle KG, Alt/Üst, İY karnesi."""
    sonuc = {}

    def _skor_gol(skor):
        try:
            ev, dep = map(int, str(skor).split("-"))
            return ev, dep
        except Exception:
            return None, None

    for market, sutun, kontrol in [
        ("2.5 Alt/Üst", "Ust25_Tahmin", None),
        ("İY 0.5", "IY05_Tahmin", None),
        ("İY 1.5", "IY15_Tahmin", None),
    ]:
        if sutun not in df.columns:
            continue
        dogru = yanlis = 0
        for _, satir in df.iterrows():
            tahmin = str(satir.get(sutun, ""))
            if market.startswith("İY"):
                skor = str(satir.get("IY_Skor", ""))
            else:
                skor = str(satir.get("MS_Skor", ""))

            if skor in ["-", "Oynanmadı", "", "nan"]:
                continue
            ev, dep = _skor_gol(skor)
            if ev is None:
                continue
            toplam = ev + dep

            esik = 2.5 if "2.5" in market else (0.5 if "0.5" in market else 1.5)
            gercek = "ÜST" if toplam > esik else "ALT"
            if tahmin == gercek:
                dogru += 1
            elif tahmin in ["ÜST", "ALT"]:
                yanlis += 1

        if dogru + yanlis > 0:
            sonuc[market] = {
                "isabet": round(dogru / (dogru + yanlis) * 100, 1),
                "dogru": dogru, "yanlis": yanlis
            }

    return sonuc
