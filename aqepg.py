import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import urllib.parse
import unicodedata
import re

DIGITURK_DAYS = 2
BELGESELSEMO_URL = "https://belgeselsemo.com.tr/yayin-akisi2/xml/turkey3.xml"
OUTPUT_FILE = "epg.xml"

def normalize_tvg_id(name):
    name = name.lower()
    name = unicodedata.normalize("NFD", name)
    name = name.encode("ascii", "ignore").decode("utf-8")
    name = re.sub(r"[^a-z0-9]+", "", name)
    return name

def fetch_digiturk_epg():
    print("📡 Digiturk EPG çekiliyor...")
    tv = ET.Element("tv")
    today = datetime.now()

    for gun in range(DIGITURK_DAYS):
        tarih = today + timedelta(days=gun)
        base_date_str = tarih.strftime("%m/%d/%Y") + " 00:00:00"
        encoded_date = urllib.parse.quote(base_date_str)

        url = f"https://www.digiturk.com.tr/Ajax/GetTvGuideFromDigiturk?Day={encoded_date}"
        headers = {
            "user-agent": "Mozilla/5.0",
            "x-requested-with": "XMLHttpRequest"
        }
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        channels = soup.select("div.swiper-slide.channelContent")

        for channel in channels:
            name_elem = channel.select_one("h3.tvguide-channel-name")
            if not name_elem:
                continue
            channel_name = name_elem.get_text(strip=True)
            tvg_id = normalize_tvg_id(channel_name)

            channel_elem = tv.find(f"./channel[@id='{tvg_id}']")
            if channel_elem is None:
                channel_elem = ET.SubElement(tv, "channel", id=tvg_id)
                ET.SubElement(channel_elem, "display-name").text = channel_name

            programs = channel.select("div.tvGuideResult-box-wholeDates.channelDetail")
            for prog in programs:
                time_span = prog.select_one("span.tvGuideResult-box-wholeDates-time-hour")
                duration_span = prog.select_one("span.tvGuideResult-box-wholeDates-time-totalMinute")
                title_span = prog.select_one("span.tvGuideResult-box-wholeDates-title")
                if not time_span or not title_span:
                    continue

                start_time_str = time_span.get_text(strip=True)
                duration_str = duration_span.get_text(strip=True) if duration_span else "30"
                title = title_span.get("title") or title_span.get_text(strip=True)

                start_dt = datetime.strptime(base_date_str, "%m/%d/%Y %H:%M:%S")
                hour, minute = map(int, start_time_str.split(":"))
                start_dt = start_dt.replace(hour=hour, minute=minute, second=0)

                duration_minutes = int("".join(filter(str.isdigit, duration_str))) or 30
                stop_dt = start_dt + timedelta(minutes=duration_minutes)

                # Kayma düzeltme (15 dakika)
                if gun == 0:
                    fark_dk = abs((start_dt - datetime.now()).total_seconds()) / 60
                    if fark_dk > 15:
                        start_dt = datetime.now().replace(second=0, microsecond=0)
                        stop_dt = start_dt + timedelta(minutes=duration_minutes)

                programme = ET.SubElement(tv, "programme", {
                    "start": start_dt.strftime("%Y%m%d%H%M%S +0300"),
                    "stop": stop_dt.strftime("%Y%m%d%H%M%S +0300"),
                    "channel": tvg_id
                })
                ET.SubElement(programme, "title").text = title

    return tv

def fetch_belgeselsemo_epg():
    print("📡 Belgeselsemo EPG indiriliyor...")
    r = requests.get(BELGESELSEMO_URL, timeout=15)
    r.raise_for_status()
    return ET.fromstring(r.content)

def merge_epgs(digiturk_tv, belgeselsemo_tv):
    print("🔄 EPG'ler birleştiriliyor...")
    for channel in belgeselsemo_tv.findall("channel"):
        tvg_id = normalize_tvg_id(channel.findtext("display-name"))
        if digiturk_tv.find(f"./channel[@id='{tvg_id}']") is None:
            channel.set("id", tvg_id)
            digiturk_tv.append(channel)

    for prog in belgeselsemo_tv.findall("programme"):
        tvg_id = normalize_tvg_id(prog.get("channel"))
        prog.set("channel", tvg_id)
        digiturk_tv.append(prog)

    return digiturk_tv

if __name__ == "__main__":
    digiturk_epg = fetch_digiturk_epg()
    belgeselsemo_epg = fetch_belgeselsemo_epg()
    merged = merge_epgs(digiturk_epg, belgeselsemo_epg)

    tree = ET.ElementTree(merged)
    tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
    print(f"✅ {OUTPUT_FILE} oluşturuldu.")
