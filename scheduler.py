"""
MacApp Pro — Otomatik Zamanlayıcı Modülü
==========================================
Bu dosya app.py'nin yanına koyulur ve başlangıçta import edilir.
Görevler:
  - Her gün 10:00 → bülteni çek, tüm maçları analiz et, Radar tablosuna kaydet
  - Her 30 dakika → bekleyen maçların süresini kontrol et (bitti mi?)
  - Her gün 00:05 → bir önceki günü kapat, özet hazırla
"""

import threading
import logging
import json
import os
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import live_scores  # live_scores.py aynı klasörde olmalı

# ── Loglama ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    filename="macapp_scheduler.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("macapp_scheduler")

# ── Durum dosyası (JSON) ──────────────────────────────────────────────────────
DURUM_DOSYASI = "scheduler_durum.json"

def durum_yukle() -> dict:
    """Zamanlayıcı çalışma geçmişini dosyadan yükler."""
    if os.path.exists(DURUM_DOSYASI):
        try:
            with open(DURUM_DOSYASI, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "son_bulten_tarama": None,
        "son_kapama": None,
        "bugun_analiz_sayisi": 0,
        "toplam_analiz": 0,
        "hatalar": [],
    }

def durum_kaydet(durum: dict):
    """Durum sözlüğünü JSON'a yazar."""
    try:
        with open(DURUM_DOSYASI, "w", encoding="utf-8") as f:
            json.dump(durum, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        log.error(f"Durum kaydedilemedi: {e}")


# ── Görev 1: Günlük bülten taraması ─────────────────────────────────────────

def gunluk_bulten_gorevi(app_modulu):
    """
    Her gün 10:00'da çalışır.
    1. Bülteni kazır (bulteni_kazi).
    2. Her maçı KNN ile analiz eder (analiz_et).
    3. Sonuçları Radar tablosuna kaydeder.
    4. Telegram bildirimi gönderir (varsa).
    """
    log.info("=== GÜNLÜK BÜLTEN GÖREVİ BAŞLADI ===")
    durum = durum_yukle()

    try:
        # 1. Bülteni çek
        log.info("Bülten çekiliyor...")
        guncel_bulten = app_modulu.bulteni_kazi()
        log.info(f"Bültende {len(guncel_bulten)-1} maç bulundu.")

        # 2. Radar tablosunu yükle
        df_radar = app_modulu.radar_dosyasi_yukle()
        bugun = pd.Timestamp.now().strftime("%Y-%m-%d")
        bugun_kayitli = set(
            df_radar[df_radar["Tarih"] == bugun]["Mac"].tolist()
        ) if len(df_radar) > 0 else set()

        sonraki_id = int(df_radar["ID"].max()) + 1 if len(df_radar) > 0 else 1

        # 3. Her maçı analiz et
        yeni_satirlar = []
        oneriler = []  # Telegram mesajı için

        df_takip = app_modulu.takip_dosyasi_yukle()
        tamamlananlar = df_takip[df_takip["Durum"] == "Tamamlandı"]
        trend = 1.04 if len(tamamlananlar) > 0 else 1.00

        def iy_gol_hesapla(x):
            try:
                a, b = x.split(" - ")
                return int(a) + int(b)
            except Exception:
                return 0

        for mac_adi, oranlar in guncel_bulten.items():
            if mac_adi == "Manuel Giriş (Özel Maç Tanımla)":
                continue
            if mac_adi in bugun_kayitli:
                log.info(f"Atlandı (zaten kayıtlı): {mac_adi}")
                continue

            try:
                t_marj = (
                    (1 / oranlar["ms1"])
                    + (1 / oranlar["ms0"])
                    + (1 / oranlar["ms2"])
                )
                ph = (1 / oranlar["ms1"]) / t_marj
                pd_oran = (1 / oranlar["ms0"]) / t_marj
                pa = (1 / oranlar["ms2"]) / t_marj
                pover = (1 / oranlar["ust"]) / 1.06

                (
                    ms_oranlari, kg_yuzdesi, ust_yuzdesi,
                    tablo_df, iy_ms, _, _, _, _, _
                ) = app_modulu.analiz_et(ph, pd_oran, pa, pover, trend)

                iy_goller = tablo_df["İlk Yarı Skoru"].apply(iy_gol_hesapla)
                iy_05 = round((iy_goller > 0).mean() * 100, 1)
                iy_15 = round((iy_goller > 1).mean() * 100, 1)

                ms_en_yuksek = max(
                    {"MS 1": ph, "MS X": pd_oran, "MS 2": pa},
                    key=lambda k: {"MS 1": ph, "MS X": pd_oran, "MS 2": pa}[k],
                )
                kg_tahmin = "VAR" if kg_yuzdesi >= 50 else "YOK"
                ust_tahmin = "ÜST" if ust_yuzdesi >= 50 else "ALT"
                iy05_tahmin = "ÜST" if iy_05 >= 50 else "ALT"
                iy15_tahmin = "ÜST" if iy_15 >= 50 else "ALT"

                yeni_satirlar.append({
                    "ID": sonraki_id,
                    "Tarih": bugun,
                    "Mac": mac_adi,
                    "MS_Tahmin": ms_en_yuksek,
                    "KG_Tahmin": kg_tahmin,
                    "Ust25_Tahmin": ust_tahmin,
                    "IY05_Tahmin": iy05_tahmin,
                    "IY15_Tahmin": iy15_tahmin,
                    "IY_Skor": "Oynanmadı",
                    "MS_Skor": "Oynanmadı",
                    "Durum": "Bekliyor",
                })
                sonraki_id += 1

                # Yüksek güven eşiği → öneri listesine ekle
                if kg_yuzdesi >= 65 or ust_yuzdesi >= 65:
                    oneriler.append({
                        "mac": mac_adi,
                        "kg": kg_yuzdesi,
                        "ust": ust_yuzdesi,
                        "ms": ms_en_yuksek,
                    })

                log.info(
                    f"Analiz OK: {mac_adi} | MS:{ms_en_yuksek} "
                    f"KG:{kg_yuzdesi}% ÜST:{ust_yuzdesi}%"
                )
            except Exception as hata:
                log.warning(f"Analiz HATASI ({mac_adi}): {hata}")
                continue

        # 4. Kaydet
        if yeni_satirlar:
            df_yeni = pd.DataFrame(yeni_satirlar)
            df_radar = pd.concat([df_radar, df_yeni], ignore_index=True)
            app_modulu.radar_dosyasi_kaydet(df_radar)
            log.info(f"{len(yeni_satirlar)} maç Radar tablosuna eklendi.")

        # 5. Özet dosyasını güncelle
        durum["son_bulten_tarama"] = datetime.now().isoformat()
        durum["bugun_analiz_sayisi"] = len(yeni_satirlar)
        durum["toplam_analiz"] = durum.get("toplam_analiz", 0) + len(yeni_satirlar)
        durum_kaydet(durum)

        # 6. Telegram bildirimi (isteğe bağlı)
        _telegram_bildir_gunluk(oneriler, len(yeni_satirlar), app_modulu)

        log.info("=== GÜNLÜK BÜLTEN GÖREVİ TAMAMLANDI ===")

    except Exception as genel_hata:
        log.error(f"Görev çöktü: {genel_hata}", exc_info=True)
        durum.setdefault("hatalar", []).append({
            "zaman": datetime.now().isoformat(),
            "hata": str(genel_hata),
        })
        durum_kaydet(durum)


# ── Görev 2: Canlı skor güncelleme ───────────────────────────────────────────

def canli_skor_gorevi(app_modulu):
    """
    Her 30 dakikada (14:00-23:30 arası) çalışır.
    Bekleyen maçların skorunu API-Football'dan çeker ve günceller.
    """
    log.info("=== CANLI SKOR GÖREVİ BAŞLADI ===")
    durum = durum_yukle()
    try:
        guncellenen = live_scores.bekleyen_maclari_guncelle(app_modulu)
        log.info(f"Canlı skor: {guncellenen} maç güncellendi.")

        # API kota bilgisini logla
        kota = live_scores.api_kota_kontrol()
        log.info(
            f"API kota: {kota['kullanilan']}/{kota['limit']} "
            f"(Plan: {kota['plan']})"
        )

        durum["son_canli_skor"] = datetime.now().isoformat()
        durum["son_guncellenen_mac_sayisi"] = guncellenen
        durum_kaydet(durum)

        # Güncelleme olduysa Telegram'a bildir
        if guncellenen > 0:
            _telegram_bildir_skor(guncellenen, app_modulu)

    except Exception as hata:
        log.error(f"Canlı skor görevi hatası: {hata}", exc_info=True)
    log.info("=== CANLI SKOR GÖREVİ TAMAMLANDI ===")


def _telegram_bildir_skor(guncellenen: int, app_modulu):
    """Güncellenen skorları Telegram'a bildirir."""
    try:
        import streamlit as st
        import requests as req

        token = st.secrets.get("TELEGRAM_TOKEN", "")
        chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            return

        metin = (
            f"⚽ <b>MacApp Skor Güncellemesi</b>\n"
            f"🔄 {guncellenen} maçın sonucu otomatik güncellendi.\n"
            f"📊 Başarı karnesini görmek için uygulamayı aç."
        )
        req.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": metin, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        log.warning(f"Telegram skor bildirimi gönderilemedi: {e}")


# ── Görev 3: Günü kapatma özeti ──────────────────────────────────────────────

def gunluk_kapama_gorevi(app_modulu):
    """
    Her gün 00:05'te çalışır.
    Bir önceki günün bekleyen maçlarını işaretler, özet üretir.
    """
    log.info("=== GÜNLÜK KAPAMA GÖREVİ BAŞLADI ===")
    durum = durum_yukle()
    try:
        df_radar = app_modulu.radar_dosyasi_yukle()
        dun = (pd.Timestamp.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        # Dünden hâlâ "Bekliyor" olanları "Oynanmadı - Kapalı" yap
        mask = (df_radar["Tarih"] == dun) & (df_radar["Durum"] == "Bekliyor")
        kapatilan = mask.sum()
        if kapatilan > 0:
            df_radar.loc[mask, "Durum"] = "Veri Girilmedi"
            app_modulu.radar_dosyasi_kaydet(df_radar)
            log.info(f"{kapatilan} maç 'Veri Girilmedi' olarak kapatıldı.")

        durum["son_kapama"] = datetime.now().isoformat()
        durum["bugun_analiz_sayisi"] = 0
        durum_kaydet(durum)
        log.info("=== KAPAMA GÖREVİ TAMAMLANDI ===")

    except Exception as hata:
        log.error(f"Kapama görevi hatası: {hata}", exc_info=True)


# ── Telegram yardımcısı ───────────────────────────────────────────────────────

def _telegram_bildir_gunluk(oneriler: list, analiz_sayisi: int, app_modulu):
    """Günlük bülten özetini Telegram'a gönderir. Secrets yoksa sessizce atlar."""
    try:
        import streamlit as st
        import requests

        token = st.secrets.get("TELEGRAM_TOKEN", "")
        chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            return

        tarih = datetime.now().strftime("%d %B %Y")
        metin = f"🤖 <b>MacApp Günlük Bülten</b>\n📅 {tarih}\n\n"
        metin += f"📊 Toplam analiz edilen maç: <b>{analiz_sayisi}</b>\n\n"

        if oneriler:
            metin += "🔥 <b>Yüksek güven önerileri:</b>\n"
            for o in oneriler[:5]:  # En fazla 5 öneri
                metin += (
                    f"  ⚽ {o['mac']}\n"
                    f"     {o['ms']} | KG:{o['kg']}% | Üst:{o['ust']}%\n"
                )
        else:
            metin += "ℹ️ Bugün yüksek güvenli öneri çıkmadı."

        metin += "\n\n<i>Detaylı analiz için uygulamayı aç.</i>"

        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": metin, "parse_mode": "HTML"},
            timeout=10,
        )
        log.info("Telegram bildirimi gönderildi.")
    except Exception as e:
        log.warning(f"Telegram bildirimi gönderilemedi: {e}")


# ── Zamanlayıcı başlatıcı ─────────────────────────────────────────────────────

_scheduler_instance = None
_scheduler_lock = threading.Lock()


def zamanlayici_baslat(app_modulu):
    """
    Streamlit uygulamasının en üstünde bir kez çağrılır.
    Thread-safe: birden fazla worker process'te çift başlatmayı önler.

    Kullanım (app.py'de):
        import scheduler
        scheduler.zamanlayici_baslat(sys.modules[__name__])
    """
    global _scheduler_instance

    with _scheduler_lock:
        if _scheduler_instance is not None and _scheduler_instance.running:
            return  # Zaten çalışıyor

        sched = BackgroundScheduler(
            timezone="Europe/Istanbul",
            job_defaults={"coalesce": True, "max_instances": 1},
        )

        # Görev 1: Her gün saat 10:00'da bülten tarama
        sched.add_job(
            func=gunluk_bulten_gorevi,
            trigger=CronTrigger(hour=10, minute=0),
            args=[app_modulu],
            id="gunluk_bulten",
            name="Günlük Bülten Taraması",
            replace_existing=True,
        )

        # Görev 2: Her 30 dakikada canlı skor güncelle (14:00-23:30 arası)
        sched.add_job(
            func=canli_skor_gorevi,
            trigger=CronTrigger(hour="14-23", minute="0,30"),
            args=[app_modulu],
            id="canli_skor",
            name="Canlı Skor Güncellemesi",
            replace_existing=True,
        )

        # Görev 3: Her gün 00:05'te günü kapat
        sched.add_job(
            func=gunluk_kapama_gorevi,
            trigger=CronTrigger(hour=0, minute=5),
            args=[app_modulu],
            id="gunluk_kapama",
            name="Günlük Kapama",
            replace_existing=True,
        )

        sched.start()
        _scheduler_instance = sched

        log.info(
            "Zamanlayıcı başlatıldı. "
            "Görevler: bülten=10:00, canlı_skor=14-23:*/30, kapama=00:05 (Europe/Istanbul)"
        )
        return sched


def zamanlayici_durdur():
    """Uygulama kapatılırken çağrılır."""
    global _scheduler_instance
    with _scheduler_lock:
        if _scheduler_instance and _scheduler_instance.running:
            _scheduler_instance.shutdown(wait=False)
            log.info("Zamanlayıcı durduruldu.")


def zamanlayici_durumu() -> dict:
    """Şu anki görev listesini döndürür — UI'da göstermek için."""
    global _scheduler_instance
    if _scheduler_instance is None or not _scheduler_instance.running:
        return {"aktif": False, "gorevler": []}

    gorevler = []
    for job in _scheduler_instance.get_jobs():
        gorevler.append({
            "id": job.id,
            "isim": job.name,
            "sonraki_calisma": str(job.next_run_time),
        })

    durum = durum_yukle()
    return {
        "aktif": True,
        "gorevler": gorevler,
        "son_tarama": durum.get("son_bulten_tarama"),
        "bugun_analiz": durum.get("bugun_analiz_sayisi", 0),
        "toplam_analiz": durum.get("toplam_analiz", 0),
        "son_canli_skor": durum.get("son_canli_skor"),
        "son_guncellenen": durum.get("son_guncellenen_mac_sayisi", 0),
    }


def manuel_bulten_calistir(app_modulu):
    """
    UI'dan 'Şimdi Çalıştır' butonuna basıldığında doğrudan çağrılır.
    Arka planda thread açar — Streamlit'i bloklamaz.
    """
    t = threading.Thread(
        target=gunluk_bulten_gorevi,
        args=[app_modulu],
        daemon=True,
        name="manuel_bulten",
    )
    t.start()
    log.info("Manuel bülten görevi tetiklendi.")
    return t
