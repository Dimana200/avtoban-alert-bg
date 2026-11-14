import re, html, urllib.request, urllib.parse, os
UA = {"User-Agent": "Mozilla/5.0 (AvtobanAlertBG)"}
def get(path):
    u = "https://www.mvr.bg" + urllib.parse.quote(path)
    try:
        return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40).read()
    except Exception as e:
        print("ERR", path, e); return b""
os.makedirs("out", exist_ok=True)
pages = {
 "yambol": "/yambol/обществен-ред-и-сигурност/мвр-съветва/полезна-информация/разположение-на-стационарни-и-мобилни-камери-за-установяване-на-нарушения-по-здвп-на-територията-на-област-ямбол",
 "smolyan": "/smolyan/обществен-ред-и-сигурност/мвр-съветва/полезна-информация/58680",
 "lovech": "/lovech/обществен-ред-и-сигурност/мвр-съветва/полезна-информация/111021",
 "silistra": "/silistra/обществен-ред-и-сигурност/мвр-съветва/полезна-информация/56335",
 "silistra2": "/silistra/обществен-ред-и-сигурност/пътен-контрол/mesta_mts",
 "sliven": "/sliven/обществен-ред-и-сигурност/мвр-съветва/полезна-информация/58265",
 "haskovo": "/haskovo/обществен-ред-и-сигурност/мвр-съветва/полезна-информация/места-и-точки-за-контрол-на-скоростта",
 "targovishte": "/targovishte/обществен-ред-и-сигурност/мвр-съветва/полезна-информация/kamera",
}
for k, p in pages.items():
    s = get(p).decode("utf-8", "replace")
    open(f"out/{k}.html", "w").write(s)
    dates = sorted(set(re.findall(r"\b\d{1,2}[./]\d{1,2}[./]20\d\d\b|\b20\d\d-\d\d-\d\d\b", s)))
    files = sorted(set(urllib.parse.unquote(f) for f in re.findall(r'(?:href|src)="([^"]+\.(?:pdf|xlsx?|docx?|jpe?g|png))"', s, re.I) if "upload" in f or "docs" in f))
    print("PAGE", k, len(s), "dates", dates[:8], "files", files[:6])
    for i, f in enumerate(files[:4]):
        if f.lower().endswith((".pdf", ".xls", ".xlsx", ".doc", ".docx")):
            b = get(f if f.startswith("/") else "/" + f.split("mvr.bg", 1)[-1])
            ext = f.rsplit(".", 1)[1].lower()
            open(f"out/{k}_f{i}.{ext}", "wb").write(b); print("  FILE", k, i, len(b), f)
