BASE_URL = "https://canliyayin.umitm0d.workers.dev/"
output = []

input_file = "1UmitTV.m3u"
output_file = "playlist.m3u"

try:
    with open(input_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
except FileNotFoundError:
    print(f"{input_file} dosyası bulunamadı!")
    exit(1)

for line in lines:
    if line.strip().startswith("http"):
        stream_name = line.strip().split("/")[-1].split("?")[0]
        output.append(BASE_URL + stream_name + "\n")
    else:
        output.append(line)

with open(output_file, "w", encoding="utf-8") as f:
    f.writelines(output)

print(f"{output_file} başarıyla oluşturuldu!")
