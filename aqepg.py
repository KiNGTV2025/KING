import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import urllib.parse
import unicodedata
import re

DIGITURK_GUN_SAYISI = 2
BELGESELSEMO_URL = "https://belgeselsemo.com.tr/yayin-akisi2/xml/turkey3.xml"

KANALLAR_DOSYA = "kanallar.txt"
EPG_CIKTI = "epg.xml"

def normalize_tvg_id(name):
    """Kanal adından tvg-id oluşturur"""
    name = name.lower()
    name = unicodedata.normalize("NFD", name)
    name = name.encode("ascii", "ignore").decode("utf-8")
    name = re.sub(r"[^a-z0-9]+", "", name)
    return name

# 1️⃣ Digiturk'ten kanal listesi ve programları al
def get_digiturk_epg():
    kanallar_dict = {}
    tv = ET.Element("tv")
    today = datetime.now()

    for gun in range(DIGITURK_GUN_SAYISI):
        tarih = today + timedelta(days=gun)
        base_date_str = tarih.strftime("%m/%d/%Y") + " 00:00:00"
        encoded_date = urllib.parse.quote(base_date_str)

        url = f"https://www.digiturk.com.tr/Ajax/GetTvGuideFromDigiturk?Day={encoded_date}"
        headers = {
            "accept": "*/*",
            "referer": "https://www.digiturk.com.tr/yayin-akisi",
            "user-agent": "Mozilla/5.0",
            "x-requested-with": "XMLHttpRequest"
        }

        r = requests.get(url, headers=headers)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        channels = soup.select("div.swiper-slide.channelContent")

        for channel in channels:
            h3 = channel.select_one("h3.tvguide-channel-name")
            channel_name = h3.get_text(strip=True) if h3 else "Bilinmeyen Kanal"
            tvg_id = normalize_tvg_id(channel_name)
            kanallar_dict[channel_name] = tvg_id

            channel_elem = tv.find(f"./channel[@id='{tvg_id}']")
            if channel_elem is None:
                channel_elem = ET.SubElement(tv, "channel", id=tvg_id)
                ET.SubElement(channel_elem, "display-name").text = channel_name

            programs = channel.select("div.tvGuideResult-box-wholeDates.channelDetail")
            for prog in programs:
                time_span = prog.select_one("span.tvGuideResult-box-wholeDates-time-hour")
                duration_span = prog.select_one("span.tvGuideResult-box-wholeDates-time-totalMinute")
                title_span = prog.select_one("span.tvGuideResult-box-wholeDates-title")

                if not time_span:
                    continue

                start_time_str = time_span.get_text(strip=True)
                duration_str = duration_span.get_text(strip=True) if duration_span else "30"
                title = title_span.get("title") or title_span.get_text(strip=True) if title_span else "Bilinmeyen Program"

                start_dt = datetime.strptime(base_date_str, "%m/%d/%Y %H:%M:%S")
                hour, minute = map(int, start_time_str.split(":"))
                start_dt = start_dt.replace(hour=hour, minute=minute, second=0)
                stop_dt = start_dt + timedelta(minutes=int("".join(filter(str.isdigit, duration_str))) or 30)

                programme = ET.SubElement(tv, "programme", {
                    "start": start_dt.strftime("%Y%m%d%H%M%S +0300"),
                    "stop": stop_dt.strftime("%Y%m%d%H%M%S +0300"),
                    "channel": tvg_id
                })
                ET.SubElement(programme, "title").text = title

    return tv, kanallar_dict

# 2️⃣ Belgeselsemo EPG'sini çek ve Digiturk tvg-id'lerine göre güncelle
def merge_belgeselsemo(tv_root, kanallar_dict):
    print("📥 Belgeselsemo XML indiriliyor...")
    r = requests.get(BELGESELSEMO_URL, timeout=15)
    r.raise_for_status()
    belgesel_tree = ET.fromstring(r.content)

    belgesel_map = {}
    for ch in belgesel_tree.findall("channel"):
        name_elem = ch.find("display-name")
        if name_elem is not None:
            ch_name = name_elem.text.strip()
            belgesel_map[ch.get("id")] = ch_name

    for prog in belgesel_tree.findall("programme"):
        ch_id = prog.get("channel")
        ch_name = belgesel_map.get(ch_id, ch_id)
        digiturk_tvg_id = kanallar_dict.get(ch_name)
        if not digiturk_tvg_id:
            continue

        start = datetime.strptime(prog.get("start")[:12], "%Y%m%d%H%M") + timedelta(hours=3)
        stop = datetime.strptime(prog.get("stop")[:12], "%Y%m%d%H%M") + timedelta(hours=3)

        programme = ET.SubElement(tv_root, "programme", {
            "start": start.strftime("%Y%m%d%H%M%S +0300"),
            "stop": stop.strftime("%Y%m%d%H%M%S +0300"),
            "channel": digiturk_tvg_id
        })

        title_elem = prog.find("title")
        ET.SubElement(programme, "title").text = title_elem.text if title_elem is not None else "Bilinmeyen Program"

# 3️⃣ Ana çalışma
if __name__ == "__main__":
    print("📡 Digiturk EPG çekiliyor...")
    tv_root, kanallar_dict = get_digiturk_epg()

    print("📄 Kanal listesi kaydediliyor...")
    with open(KANALLAR_DOSYA, "w", encoding="utf-8") as f:
        for ad, tid in sorted(kanallar_dict.items()):
            f.write(f"{ad} => {tid}\n")

    print("🔄 Belgeselsemo ile birleştiriliyor...")
    merge_belgeselsemo(tv_root, kanallar_dict)

    print("💾 EPG XML kaydediliyor...")
    tree = ET.ElementTree(tv_root)
    tree.write(EPG_CIKTI, encoding="utf-8", xml_declaration=True)

    print(f"✅ {EPG_CIKTI} oluşturuldu, {KANALLAR_DOSYA} hazır.")
