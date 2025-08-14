import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import urllib.parse
import unicodedata
import re
from collections import defaultdict
import concurrent.futures

DIGITURK_GUN_SAYISI = 2
BELGESELSEMO_URL = "https://belgeselsemo.com.tr/yayin-akisi2/xml/turkey3.xml"
KANALLAR_DOSYA = "kanallar.txt"
EPG_CIKTI = "epg.xml"
KAYMA_TOLERANSI_DK = 15

# ---------------------------
# PROXY TOPLAMA FONKSİYONLARI
# ---------------------------

def get_tr_proxies():
    proxies = set()

    # 1. Kaynak: proxy-list.download
    try:
        url = "https://www.proxy-list.download/api/v1/get?type=http&country=TR"
        r = requests.get(url, timeout=10)
        if r.ok:
            for line in r.text.splitlines():
                if ":" in line:
                    proxies.add(line.strip())
    except:
        pass

    # 2. Kaynak: free-proxy-list.net
    try:
        url = "https://free-proxy-list.net/"
        soup = BeautifulSoup(requests.get(url, timeout=10).text, "html.parser")
        table = soup.find("table", id="proxylisttable")
        if table:
            for row in table.tbody.find_all("tr"):
                cols = row.find_all("td")
                if len(cols) >= 2 and cols[2].text.strip().upper() == "TR":
                    ip = cols[0].text.strip()
                    port = cols[1].text.strip()
                    proxies.add(f"{ip}:{port}")
    except:
        pass

    # 3. Kaynak: spys.me
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get("https://spys.me/proxy.txt", headers=headers, timeout=10)
        if r.ok:
            for line in r.text.splitlines():
                if "TR" in line:
                    parts = line.split()
                    if parts and ":" in parts[0]:
                        proxies.add(parts[0])
    except:
        pass

    return list(proxies)

def test_proxy(proxy):
    test_url = "https://www.digiturk.com.tr/Ajax/GetTvGuideFromDigiturk?Day=08/14/2025%2000%3A00%3A00"
    headers = {
        "accept": "*/*",
        "referer": "https://www.digiturk.com.tr/yayin-akisi",
        "user-agent": "Mozilla/5.0",
        "x-requested-with": "XMLHttpRequest"
    }
    try:
        r = requests.get(test_url, headers=headers, proxies={"http": f"http://{proxy}", "https": f"http://{proxy}"}, timeout=5)
        if r.status_code == 200:
            return proxy
    except:
        return None
    return None

def get_working_proxy():
    print("🌐 Türkiye proxy listesi çekiliyor...")
    proxy_list = get_tr_proxies()
    print(f"🔍 {len(proxy_list)} adet TR proxy bulundu.")

    if not proxy_list:
        print("❌ Hiç proxy bulunamadı!")
        return None

    print("⚡ Proxy test ediliyor...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(test_proxy, p): p for p in proxy_list}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                print(f"✅ Çalışan proxy bulundu: {result}")
                return result

    print("❌ Hiçbir proxy çalışmadı.")
    return None

# ---------------------------
# EPG FONKSİYONLARI
# ---------------------------

def normalize_tvg_id(name):
    name = name.lower()
    name = unicodedata.normalize("NFD", name)
    name = name.encode("ascii", "ignore").decode("utf-8")
    name = re.sub(r"[^a-z0-9]+", "", name)
    return name

def temizle_hd_tr(name):
    return re.sub(r"(hd|\.tr|_tr)$", "", name, flags=re.IGNORECASE)

def get_digiturk_epg(proxy=None):
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

        proxies = None
        if proxy:
            proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}

        r = requests.get(url, headers=headers, proxies=proxies, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        channels = soup.select("div.swiper-slide.channelContent")

        for channel in channels:
            h3 = channel.select_one("h3.tvguide-channel-name")
            channel_name = h3.get_text(strip=True) if h3 else "Bilinmeyen Kanal"
            tvg_id = normalize_tvg_id(channel_name)
            kanallar_dict[channel_name] = {"digiturk": tvg_id}

            if tv.find(f"./channel[@id='{tvg_id}']") is None:
                ch_elem = ET.SubElement(tv, "channel", id=tvg_id)
                ET.SubElement(ch_elem, "display-name").text = channel_name

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
                start_dt = start_dt.replace(hour=hour, minute=minute)
                stop_dt = start_dt + timedelta(minutes=int("".join(filter(str.isdigit, duration_str))) or 30)

                programme_elem = ET.SubElement(tv, "programme", {
                    "start": start_dt.strftime("%Y%m%d%H%M%S +0300"),
                    "stop": stop_dt.strftime("%Y%m%d%H%M%S +0300"),
                    "channel": tvg_id
                })
                ET.SubElement(programme_elem, "title").text = title

    return tv, kanallar_dict

def merge_belgeselsemo(tv_root, kanallar_dict):
    print("📥 Belgeselsemo XML indiriliyor...")
    r = requests.get(BELGESELSEMO_URL, timeout=15)
    r.raise_for_status()
    belgesel_tree = ET.fromstring(r.content)

    belgesel_map = {}
    for ch in belgesel_tree.findall("channel"):
        name_elem = ch.find("display-name")
        if name_elem is not None:
            ch_name = temizle_hd_tr(name_elem.text.strip())
            belgesel_map[ch.get("id")] = ch_name
            if ch_name in kanallar_dict:
                kanallar_dict[ch_name]["belgeselsemo"] = normalize_tvg_id(ch_name)
            else:
                kanallar_dict[ch_name] = {"belgeselsemo": normalize_tvg_id(ch_name)}

    kayma_dict = defaultdict(list)
    digiturk_programs = defaultdict(list)

    for prog in tv_root.findall("programme"):
        digiturk_programs[prog.get("channel")].append(prog.get("start"))

    for prog in belgesel_tree.findall("programme"):
        ch_id = prog.get("channel")
        ch_name = belgesel_map.get(ch_id, ch_id)
        digiturk_tvg_id = kanallar_dict.get(ch_name, {}).get("digiturk")
        if not digiturk_tvg_id:
            continue
        start_b = datetime.strptime(prog.get("start")[:12], "%Y%m%d%H%M") + timedelta(hours=3)
        if digiturk_programs[digiturk_tvg_id]:
            first_d = datetime.strptime(digiturk_programs[digiturk_tvg_id][0][:12], "%Y%m%d%H%M")
            fark = (start_b - first_d).total_seconds() / 60
            kayma_dict[digiturk_tvg_id].append(fark)

    ort_kayma = {k: sum(v)/len(v) for k, v in kayma_dict.items() if abs(sum(v)/len(v)) <= KAYMA_TOLERANSI_DK}

    for prog in belgesel_tree.findall("programme"):
        ch_id = prog.get("channel")
        ch_name = belgesel_map.get(ch_id, ch_id)
        digiturk_tvg_id = kanallar_dict.get(ch_name, {}).get("digiturk", normalize_tvg_id(ch_name))

        start = datetime.strptime(prog.get("start")[:12], "%Y%m%d%H%M") + timedelta(hours=3)
        stop = datetime.strptime(prog.get("stop")[:12], "%Y%m%d%H%M") + timedelta(hours=3)

        if digiturk_tvg_id in ort_kayma:
            start += timedelta(minutes=ort_kayma[digiturk_tvg_id])
            stop += timedelta(minutes=ort_kayma[digiturk_tvg_id])

        programme = ET.SubElement(tv_root, "programme", {
            "start": start.strftime("%Y%m%d%H%M%S +0300"),
            "stop": stop.strftime("%Y%m%d%H%M%S +0300"),
            "channel": digiturk_tvg_id
        })

        title_elem = prog.find("title")
        ET.SubElement(programme, "title").text = title_elem.text if title_elem is not None else "Bilinmeyen Program"

# ---------------------------
# MAIN
# ---------------------------

if __name__ == "__main__":
    print("📡 Digiturk EPG çekiliyor...")

    proxy = get_working_proxy()

    tv_root, kanallar_dict = get_digiturk_epg(proxy=proxy)

    print("🔄 Belgeselsemo ile birleştiriliyor...")
    merge_belgeselsemo(tv_root, kanallar_dict)

    print("📄 Kanal listesi kaydediliyor...")
    with open(KANALLAR_DOSYA, "w", encoding="utf-8") as f:
        for ad, ids in sorted(kanallar_dict.items()):
            f.write(f"{ad} => Digiturk: {ids.get('digiturk','-')} | Belgeselsemo: {ids.get('belgeselsemo','-')}\n")

    print("💾 EPG XML kaydediliyor...")
    tree = ET.ElementTree(tv_root)
    tree.write(EPG_CIKTI, encoding="utf-8", xml_declaration=True)

    print(f"✅ {EPG_CIKTI} oluşturuldu, {KANALLAR_DOSYA} hazır.")
