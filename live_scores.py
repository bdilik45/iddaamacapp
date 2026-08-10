"""
MacApp Pro — Canlı Skor Modülü
================================
API-Football kullanarak bekleyen maçların sonuçlarını otomatik çeker.
scheduler.py tarafından her 30 dakikada bir çağrılır.

Çekilen veriler:
  - MS Skoru (ev - deplasman)
  - İY Skoru
  - Toplam şut
  - Toplam korner
  - Toplam kart (sarı + kırmızı)
"""

import os
import re
import logging
import requests
import pandas as pd
from datetime import datetime, timedelta
from difflib import SequenceMatcher

log = logging.getLogger("macapp_scheduler")

# ── Sabitler ──────────────────────────────────────────────────────────────────
API_BASE = "https://v3.football.api-sports.io"
BENZERLIK_ESIGI = 0.45   # Takım adı eşleştirme hassasiyeti (0-1)
BITIS_DURUMLARI = {"FT", "AET", "PEN", "AWD", "WO"}  # Maç bitti statüleri


# ── Yardımcı fonksiyonlar ────────────────────────────────────────────────────

def _api_key() -> str:
    """Railway environment variable veya Streamlit secrets'tan API key alır."""
    # Önce environment variable dene (Railway)
    key = os.environ.get("API_FOOTBALL_KEY", "")
    if key:
        return key
    # Sonra Streamlit secrets dene (local)
    try:
        import streamlit as st
        return st.secrets.get("API_FOOTBALL_KEY", "")
    except Exception:
        return ""


def _headers() -> dict:
    return {
        "x-apisports-key": _api_key(),
        "x-rapidapi-host": "v3.football.api-sports.io",
    }


def _benzerlik(a: str, b: str) -> float:
    """İki string arasındaki benzerlik oranı (0-1)."""
    a = a.lower().strip()
    b = b.lower().strip()
    return SequenceMatcher(None, a, b).ratio()


def _takim_esles(mac_adi: str, ev_api: str, dep_api: str) -> bool:
    """
    'Fenerbahçe - Galatasaray' formatındaki maç adı ile
    API'den gelen ev/deplasman takım adlarını eşleştirir.
    """
    try:
        parca = mac_adi.split(" - ", 1)
        if len(parca) != 2:
            return False
        ev_yerel, dep_yerel = parca[0].strip(), parca[1].strip()

        ev_skor = max(
            _benzerlik(ev_yerel, ev_api),
            _benzerlik(ev_yerel, ev_api.split()[-1]),  # Sadece soyad
        )
        dep_skor = max(
            _benzerlik(dep_yerel, dep_api),
            _benzerlik(dep_yerel, dep_api.split()[-1]),
        )
        return ev_skor >= BENZERLIK_ESIGI and dep_skor >= BENZERLIK_ESIGI
    except Exception:
        return False


# ── API çağrıları ─────────────────────────────────────────────────────────────

def bugunun_maclarini_cek(tarih: str = None) -> list:
    """
    Belirtilen tarihteki (varsayılan: bugün) tüm maçları API'den çeker.
    Döndürür: fixture listesi (dict)
    """
    if not tarih:
        tarih = datetime.now().strftime("%Y-%m-%d")

    url = f"{API_BASE}/fixtures"
    params = {"date": tarih, "timezone": "Europe/Istanbul"}

    try:
        r = requests.get(url, headers=_headers(), params=params, timeout=15)
        r.raise_for_status()
        data = r.json()

        kalan = data.get("response", [])
        log.info(f"API: {tarih} için {len(kalan)} maç çekildi.")
        return kalan
    except Exception as e:
        log.error(f"API maç çekme hatası: {e}")
        return []


def mac_istatistiklerini_cek(fixture_id: int) -> dict:
    """
    Belirli bir maçın istatistiklerini çeker (şut, korner, kart).
    Döndürür: {'sut': 24, 'korner': 9, 'kart': 3}
    """
    url = f"{API_BASE}/fixtures/statistics"
    params = {"fixture": fixture_id}

    istatistik = {"sut": "-", "korner": "-", "kart": "-"}

    try:
        r = requests.get(url, headers=_headers(), params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        response = data.get("response", [])

        ev_sut = dep_sut = ev_korner = dep_korner = 0
        ev_sari = ev_kirmizi = dep_sari = dep_kirmizi = 0

        for takim_stats in response:
            stats = {s["type"]: s["value"] for s in takim_stats.get("statistics", [])}

            sut = (stats.get("Total Shots") or 0)
            korner = (stats.get("Corner Kicks") or 0)
            sari = (stats.get("Yellow Cards") or 0)
            kirmizi = (stats.get("Red Cards") or 0)

            if response.index(takim_stats) == 0:
                ev_sut, ev_korner = int(sut), int(korner)
                ev_sari, ev_kirmizi = int(sari), int(kirmizi)
            else:
                dep_sut, dep_korner = int(sut), int(korner)
                dep_sari, dep_kirmizi = int(sari), int(kirmizi)

        istatistik["sut"] = str(ev_sut + dep_sut)
        istatistik["korner"] = str(ev_korner + dep_korner)
        istatistik["kart"] = str(ev_sari + dep_sari + ev_kirmizi + dep_kirmizi)

        log.info(
            f"İstatistik #{fixture_id}: "
            f"Şut={istatistik['sut']} Korner={istatistik['korner']} Kart={istatistik['kart']}"
        )
    except Exception as e:
        log.warning(f"İstatistik çekme hatası (#{fixture_id}): {e}")

    return istatistik


# ── Ana güncelleme fonksiyonu ─────────────────────────────────────────────────

def bekleyen_maclari_guncelle(app_modulu) -> int:
    """
    Bekleyen tüm maçları API ile karşılaştırır, bittiyse günceller.
    Döndürür: güncellenen maç sayısı
    """
    api_key = _api_key()
    if not api_key:
        log.warning("API_FOOTBALL_KEY bulunamadı, canlı skor atlandı.")
        return 0

    # ── Takip tablosundaki bekleyenleri al ──
    df_takip = app_modulu.takip_dosyasi_yukle()
    bekleyenler = df_takip[df_takip["Durum"] == "Bekliyor"].copy()

    # ── Radar tablosundaki bekleyenleri al ──
    df_radar = app_modulu.radar_dosyasi_yukle()
    radar_bekleyenler = df_radar[df_radar["Durum"] == "Bekliyor"].copy()

    if len(bekleyenler) == 0 and len(radar_bekleyenler) == 0:
        log.info("Bekleyen maç yok, canlı skor sorgusu atlandı.")
        return 0

    # ── Bugün ve dünün maçlarını çek (gece geç biten maçlar için dün de) ──
    bugun = datetime.now().strftime("%Y-%m-%d")
    dun = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    api_maclar = bugunun_maclarini_cek(bugun)
    if datetime.now().hour < 4:   # Gece yarısından sonra dünü de kontrol et
        api_maclar += bugunun_maclarini_cek(dun)

    if not api_maclar:
        log.warning("API'den maç verisi gelmedi.")
        return 0

    # ── Sadece biten maçları filtrele ──
    biten_maclar = [
        m for m in api_maclar
        if m.get("fixture", {}).get("status", {}).get("short") in BITIS_DURUMLARI
    ]
    log.info(f"API'de {len(biten_maclar)} biten maç bulundu.")

    guncellenen = 0

    # ── TAKİP TABLOSU güncellemesi ──
    takip_degisti = False
    for idx, satir in bekleyenler.iterrows():
        mac_adi = str(satir.get("Mac", ""))
        eslesen = _api_mac_bul(mac_adi, biten_maclar)
        if eslesen is None:
            continue

        ms_skor, iy_skor = _skor_cikart(eslesen)
        fixture_id = eslesen["fixture"]["id"]
        istatistik = mac_istatistiklerini_cek(fixture_id)

        df_takip.loc[idx, "MS_Skor"] = ms_skor
        df_takip.loc[idx, "IY_Skor"] = iy_skor
        df_takip.loc[idx, "Sut"] = istatistik["sut"]
        df_takip.loc[idx, "Korner"] = istatistik["korner"]
        df_takip.loc[idx, "Kart"] = istatistik["kart"]
        df_takip.loc[idx, "Durum"] = "Tamamlandı"
        takip_degisti = True
        guncellenen += 1
        log.info(f"TAKİP güncellendi: {mac_adi} → {ms_skor} (İY: {iy_skor})")

    if takip_degisti:
        app_modulu.takip_dosyasi_kaydet(df_takip)

    # ── RADAR TABLOSU güncellemesi ──
    radar_degisti = False
    for idx, satir in radar_bekleyenler.iterrows():
        mac_adi = str(satir.get("Mac", ""))
        eslesen = _api_mac_bul(mac_adi, biten_maclar)
        if eslesen is None:
            continue

        ms_skor, iy_skor = _skor_cikart(eslesen)

        df_radar.loc[idx, "MS_Skor"] = ms_skor
        df_radar.loc[idx, "IY_Skor"] = iy_skor
        df_radar.loc[idx, "Durum"] = "Tamamlandı"
        radar_degisti = True
        guncellenen += 1
        log.info(f"RADAR güncellendi: {mac_adi} → {ms_skor} (İY: {iy_skor})")

    if radar_degisti:
        app_modulu.radar_dosyasi_kaydet(df_radar)

    log.info(f"Canlı skor turu tamamlandı: {guncellenen} maç güncellendi.")
    return guncellenen


# ── Yardımcı iç fonksiyonlar ──────────────────────────────────────────────────

def _api_mac_bul(mac_adi: str, api_maclar: list):
    """Maç adını API fixture listesiyle eşleştirir."""
    for m in api_maclar:
        ev = m.get("teams", {}).get("home", {}).get("name", "")
        dep = m.get("teams", {}).get("away", {}).get("name", "")
        if _takim_esles(mac_adi, ev, dep):
            return m
    return None


def _skor_cikart(fixture: dict) -> tuple:
    """
    Fixture dict'inden MS ve İY skorunu çıkarır.
    Döndürür: ('2-1', '1-0') formatında tuple
    """
    goals = fixture.get("goals", {})
    score = fixture.get("score", {})

    ms_ev = goals.get("home", 0) or 0
    ms_dep = goals.get("away", 0) or 0
    ms_skor = f"{ms_ev}-{ms_dep}"

    ht = score.get("halftime", {})
    iy_ev = ht.get("home", 0) or 0
    iy_dep = ht.get("away", 0) or 0
    iy_skor = f"{iy_ev}-{iy_dep}"

    return ms_skor, iy_skor


# ── API kota kontrolü ─────────────────────────────────────────────────────────

def api_kota_kontrol() -> dict:
    """
    Günlük kalan API kotasını döndürür.
    Streamlit UI'da göstermek için kullanılabilir.
    """
    try:
        r = requests.get(
            f"{API_BASE}/status",
            headers=_headers(),
            timeout=10,
        )
        data = r.json().get("response", {})
        return {
            "kullanilan": data.get("requests", {}).get("current", "-"),
            "limit": data.get("requests", {}).get("limit_day", 100),
            "plan": data.get("subscription", {}).get("name", "-"),
        }
    except Exception:
        return {"kullanilan": "-", "limit": 100, "plan": "-"}