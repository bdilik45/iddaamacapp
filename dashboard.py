"""
MacApp Pro — Ana Dashboard v2
================================
Düzeltmeler:
  - Son 7 günün maçlarını göster (sadece bugün değil)
  - Radar tablosundaki tamamlanan maçları da karnede hesapla
  - Analiz sekmelerine geçiş düzgün çalışsın
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

try:
    import scheduler as sched_mod
    import live_scores
    MODULLER_YUKLU = True
except ImportError:
    MODULLER_YUKLU = False


def _durum_badge(durum: str) -> str:
    if durum == "Tamamlandı":
        return "🟢"
    elif durum == "Bekliyor":
        return "🟡"
    return "⚪"


def goster(takip_dosyasi_yukle, radar_dosyasi_yukle, bulteni_kazi):

    bugun = datetime.now().strftime("%Y-%m-%d")
    simdi = datetime.now().strftime("%H:%M")
    son_7_gun = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

    # ── Başlık ──────────────────────────────────────────────────────────────
    col_bas, col_analiz, col_yenile = st.columns([3, 1, 1])
    with col_bas:
        st.markdown("## ⚽ MacApp Pro — Günlük Kontrol Paneli")
        st.caption(f"{datetime.now().strftime('%A, %d %B %Y')} · {simdi}")
    with col_analiz:
        if st.button("🔍 Maç Analiz Et", use_container_width=True, type="primary"):
            st.session_state['aktif_sayfa'] = 'analiz'
            st.rerun()
    with col_yenile:
        if st.button("🔄 Yenile", use_container_width=True):
            st.rerun()

    st.divider()

    # ── Sistem durumu ────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)

    if MODULLER_YUKLU:
        durum = sched_mod.zamanlayici_durumu()
        zam_durum = "🟢 Çalışıyor" if durum["aktif"] else "🔴 Durdu"
        bugun_analiz = durum.get("bugun_analiz", 0)
        toplam_analiz = durum.get("toplam_analiz", 0)
        son_tarama = durum.get("son_tarama")
        son_str = pd.to_datetime(son_tarama).strftime("%d/%m %H:%M") if son_tarama else "—"
        son_skor = durum.get("son_canli_skor")
        skor_str = pd.to_datetime(son_skor).strftime("%H:%M") if son_skor else "—"
        try:
            kota = live_scores.api_kota_kontrol()
            kota_str = f"{kota['kullanilan']}/{kota['limit']}"
        except Exception:
            kota_str = "—"
    else:
        zam_durum, bugun_analiz, toplam_analiz = "⚠️ Modül yok", 0, 0
        son_str, skor_str, kota_str = "—", "—", "—"

    c1.metric("Zamanlayıcı", zam_durum, f"Son: {son_str}")
    c2.metric("Bugün analiz", f"{bugun_analiz} maç", f"Toplam: {toplam_analiz}")
    c3.metric("Canlı skor", f"Son: {skor_str}", "Her 30 dakika")
    c4.metric("API kota", kota_str, "istek / gün")

    st.divider()

    # ── Veri yükle ──────────────────────────────────────────────────────────
    df_radar = radar_dosyasi_yukle()
    df_takip = takip_dosyasi_yukle()

    # Son 7 günün maçları
    if len(df_radar) > 0 and "Tarih" in df_radar.columns:
        son_maclar = df_radar[df_radar["Tarih"].isin(son_7_gun)].copy()
    else:
        son_maclar = pd.DataFrame()

    bugun_takip = pd.DataFrame()
    if len(df_takip) > 0 and "Tarih" in df_takip.columns:
        bugun_takip = df_takip[df_takip["Tarih"].isin(son_7_gun)].copy()

    # ── Bugünün önerileri (takip tablosundan) ───────────────────────────────
    st.subheader("🎯 Kaydedilen Tahminler")

    if len(bugun_takip) > 0:
        for _, satir in bugun_takip.iterrows():
            durum = str(satir.get("Durum", "Bekliyor"))
            mac = str(satir.get("Mac", ""))
            tarih = str(satir.get("Tarih", ""))
            badge = _durum_badge(durum)

            with st.container(border=True):
                st.markdown(f"**{badge} {mac}** <span style='color:#888; font-size:12px;'>{tarih}</span>", unsafe_allow_html=True)
                col_b, col_i, col_s, col_d = st.columns(4)

                banko = str(satir.get("Banko_Tahmin", "—"))
                banko_oran = satir.get("Banko_Oran", "")
                ideal = str(satir.get("Ideal_Tahmin", "—"))
                ideal_oran = satir.get("Ideal_Oran", "")
                surpriz = str(satir.get("Surpriz_Tahmin", "—"))
                surpriz_oran = satir.get("Surpriz_Oran", "")

                col_b.markdown(
                    f"<div style='background:#0f3d2e;padding:10px;border-radius:8px;border-left:3px solid #1D9E75;'>"
                    f"<div style='font-size:11px;color:#6fcfa0;'>🔒 Banko</div>"
                    f"<div style='font-size:16px;font-weight:600;color:#fff;'>{banko}</div>"
                    f"<div style='font-size:11px;color:#6fcfa0;'>oran {banko_oran}</div></div>",
                    unsafe_allow_html=True)
                col_i.markdown(
                    f"<div style='background:#0a2d4d;padding:10px;border-radius:8px;border-left:3px solid #378ADD;'>"
                    f"<div style='font-size:11px;color:#6baee8;'>💡 İdeal</div>"
                    f"<div style='font-size:16px;font-weight:600;color:#fff;'>{ideal}</div>"
                    f"<div style='font-size:11px;color:#6baee8;'>oran {ideal_oran}</div></div>",
                    unsafe_allow_html=True)
                col_s.markdown(
                    f"<div style='background:#3d2800;padding:10px;border-radius:8px;border-left:3px solid #BA7517;'>"
                    f"<div style='font-size:11px;color:#e0a94a;'>⚡ Surpriz</div>"
                    f"<div style='font-size:16px;font-weight:600;color:#fff;'>{surpriz}</div>"
                    f"<div style='font-size:11px;color:#e0a94a;'>oran {surpriz_oran}</div></div>",
                    unsafe_allow_html=True)

                if durum == "Tamamlandı":
                    ms_skor = str(satir.get("MS_Skor", ""))
                    iy_skor = str(satir.get("IY_Skor", ""))
                    sut = str(satir.get("Sut", "—"))
                    korner = str(satir.get("Korner", "—"))
                    kart = str(satir.get("Kart", "—"))
                    col_d.markdown(
                        f"<div style='background:#1a1a2e;padding:10px;border-radius:8px;'>"
                        f"<div style='font-size:11px;color:#aaa;'>Sonuç</div>"
                        f"<div style='font-size:18px;font-weight:600;color:#fff;'>{ms_skor}</div>"
                        f"<div style='font-size:11px;color:#aaa;'>İY:{iy_skor} ⚽{sut} 🚩{korner} 🟨{kart}</div></div>",
                        unsafe_allow_html=True)
                else:
                    col_d.markdown(
                        "<div style='background:#1a1a1a;padding:10px;border-radius:8px;text-align:center;'>"
                        "<div style='font-size:24px;'>⏳</div>"
                        "<div style='font-size:11px;color:#aaa;'>Bekliyor</div></div>",
                        unsafe_allow_html=True)
    else:
        col_bilgi, col_btn = st.columns([3, 1])
        col_bilgi.info("Kayıtlı tahmin yok. Sağ üstteki '🔍 Maç Analiz Et' butonuna bas.")
        with col_btn:
            if st.button("🔍 Analiz Et", use_container_width=True):
                st.session_state['aktif_sayfa'] = 'analiz'
                st.rerun()

    # ── Bülten maçları (son 7 gün) ───────────────────────────────────────────
    st.divider()

    # Tarih filtresi
    col_baslik, col_filtre = st.columns([2, 1])
    with col_baslik:
        st.subheader("📋 Bülten Maçları")
    with col_filtre:
        filtre_secim = st.selectbox(
            "Tarih",
            ["Bugün", "Son 3 gün", "Son 7 gün"],
            label_visibility="collapsed"
        )

    filtre_gunler = {
        "Bugün": [bugun],
        "Son 3 gün": [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(3)],
        "Son 7 gün": son_7_gun,
    }
    secili_gunler = filtre_gunler[filtre_secim]

    if len(df_radar) > 0 and "Tarih" in df_radar.columns:
        gosterilen = df_radar[df_radar["Tarih"].isin(secili_gunler)].copy()
    else:
        gosterilen = pd.DataFrame()

    if len(gosterilen) > 0:
        durum_sira = {"Bekliyor": 0, "Tamamlandı": 1, "Veri Girilmedi": 2}
        gosterilen["_sira"] = gosterilen["Durum"].map(durum_sira).fillna(3)
        gosterilen = gosterilen.sort_values(["Tarih", "_sira"], ascending=[False, True]).drop(columns=["_sira"])

        bekleyen = (gosterilen["Durum"] == "Bekliyor").sum()
        tamamlanan = (gosterilen["Durum"] == "Tamamlandı").sum()

        col_s1, col_s2, col_s3 = st.columns(3)
        col_s1.metric("Toplam", len(gosterilen))
        col_s2.metric("Bekleyen", bekleyen)
        col_s3.metric("Sonuçlanan", tamamlanan)

        goster_df = gosterilen[[
            "Tarih", "Mac", "MS_Tahmin", "KG_Tahmin", "Ust25_Tahmin",
            "IY05_Tahmin", "IY15_Tahmin", "MS_Skor", "IY_Skor", "Durum"
        ]].rename(columns={
            "Mac": "Maç", "MS_Tahmin": "MS", "KG_Tahmin": "KG",
            "Ust25_Tahmin": "2.5", "IY05_Tahmin": "İY0.5",
            "IY15_Tahmin": "İY1.5", "MS_Skor": "Skor", "IY_Skor": "İY"
        })

        st.dataframe(goster_df, use_container_width=True, hide_index=True,
                     height=min(500, 55 + len(gosterilen) * 35))
    else:
        st.info(f"'{filtre_secim}' için bülten maçı bulunamadı.")

    # ── Başarı karnesi ───────────────────────────────────────────────────────
    st.divider()
    st.subheader("📈 Başarı Karnesi")

    # Hem takip hem radar tablosundaki tamamlananları birleştir
    tamamlanan_takip = df_takip[df_takip["Durum"] == "Tamamlandı"].copy() if len(df_takip) > 0 else pd.DataFrame()
    tamamlanan_radar = df_radar[df_radar["Durum"] == "Tamamlandı"].copy() if len(df_radar) > 0 else pd.DataFrame()

    if len(tamamlanan_takip) == 0 and len(tamamlanan_radar) == 0:
        st.info("Henüz sonuçlanmış maç yok. Maçlar bitince karne burada oluşur.")
        return

    col_k1, col_k2 = st.columns(2)

    with col_k1:
        st.markdown("**Takip tablosu (kaydettiğin tahminler)**")
        if len(tamamlanan_takip) > 0:
            _karne_goster(tamamlanan_takip, kaynak="takip")
        else:
            st.caption("Henüz tamamlanan kayıtlı tahmin yok.")

    with col_k2:
        st.markdown("**Radar tablosu (otomatik analizler)**")
        if len(tamamlanan_radar) > 0:
            _karne_goster(tamamlanan_radar, kaynak="radar")
        else:
            st.caption("Henüz tamamlanan radar maçı yok.")


def _karne_goster(df: pd.DataFrame, kaynak: str = "takip"):
    """Market bazlı isabet oranlarını bar olarak göster."""
    karne = _karne_hesapla(df, kaynak)
    if not karne:
        st.caption("Yeterli veri yok.")
        return

    for market, veri in karne.items():
        pct = veri["isabet"]
        renk = "#1D9E75" if pct >= 65 else "#BA7517" if pct >= 50 else "#993C1D"
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:10px;margin-bottom:6px;'>"
            f"<div style='width:90px;font-size:12px;color:#ccc;'>{market}</div>"
            f"<div style='flex:1;background:#21262d;border-radius:99px;height:8px;overflow:hidden;'>"
            f"<div style='width:{pct}%;height:100%;background:{renk};border-radius:99px;'></div></div>"
            f"<div style='width:60px;font-size:12px;color:#fff;text-align:right;'>%{pct} "
            f"<span style='color:#888;font-size:10px;'>({veri['dogru']}✓ {veri['yanlis']}✗)</span></div>"
            f"</div>",
            unsafe_allow_html=True)


def _karne_hesapla(df: pd.DataFrame, kaynak: str = "takip") -> dict:
    karne = {}

    def skor_ayir(skor):
        try:
            ev, dep = map(int, str(skor).split("-"))
            return ev, dep
        except Exception:
            return None, None

    if kaynak == "takip":
        # MS tahmini — Banko_Tahmin sütunundan
        dogru = yanlis = 0
        for _, s in df.iterrows():
            tahmin = str(s.get("Banko_Tahmin", ""))
            ev, dep = skor_ayir(s.get("MS_Skor", ""))
            if ev is None or not tahmin.startswith("MS"):
                continue
            gercek = "MS 1" if ev > dep else ("MS 2" if dep > ev else "MS X")
            if gercek == tahmin:
                dogru += 1
            else:
                yanlis += 1
        if dogru + yanlis > 0:
            karne["MS 1X2"] = {"isabet": round(dogru/(dogru+yanlis)*100,1), "dogru": dogru, "yanlis": yanlis}

        # KG — Ideal_Tahmin sütunundan
        dogru = yanlis = 0
        for _, s in df.iterrows():
            tahmin = str(s.get("Ideal_Tahmin", ""))
            if "KG" not in tahmin:
                continue
            ev, dep = skor_ayir(s.get("MS_Skor", ""))
            if ev is None:
                continue
            gercek = "KG VAR" if ev > 0 and dep > 0 else "KG YOK"
            if ("VAR" in tahmin and gercek == "KG VAR") or ("YOK" in tahmin and gercek == "KG YOK"):
                dogru += 1
            else:
                yanlis += 1
        if dogru + yanlis > 0:
            karne["KG"] = {"isabet": round(dogru/(dogru+yanlis)*100,1), "dogru": dogru, "yanlis": yanlis}

    # Radar bazlı marketler (her iki kaynak için)
    for market, sutun, iy_mi, esik in [
        ("2.5 Alt/Üst", "Ust25_Tahmin", False, 2.5),
        ("İY 0.5", "IY05_Tahmin", True, 0.5),
        ("İY 1.5", "IY15_Tahmin", True, 1.5),
        ("MS", "MS_Tahmin", False, None),
    ]:
        if sutun not in df.columns:
            continue
        dogru = yanlis = 0
        for _, s in df.iterrows():
            tahmin = str(s.get(sutun, ""))
            skor_key = "IY_Skor" if iy_mi else "MS_Skor"
            ev, dep = skor_ayir(s.get(skor_key, ""))
            if ev is None:
                continue

            if market == "MS":
                gercek = "MS 1" if ev > dep else ("MS 2" if dep > ev else "MS X")
                if tahmin == gercek:
                    dogru += 1
                elif tahmin in ["MS 1", "MS 2", "MS X"]:
                    yanlis += 1
            else:
                toplam = ev + dep
                gercek = "ÜST" if toplam > esik else "ALT"
                if tahmin == gercek:
                    dogru += 1
                elif tahmin in ["ÜST", "ALT"]:
                    yanlis += 1

        if dogru + yanlis > 0:
            label = market if kaynak == "takip" else f"{market} (radar)"
            karne[label] = {"isabet": round(dogru/(dogru+yanlis)*100,1), "dogru": dogru, "yanlis": yanlis}

    return karne
