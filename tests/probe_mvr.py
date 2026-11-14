"""Find camera lists published by the regional police directorates (ОДМВР) on mvr.bg. Writes out/ pages + a summary."""
import re, html, os, urllib.request, urllib.parse
UA = {"User-Agent": "Mozilla/5.0 (AvtobanAlertBG; open data for road safety)"}
def get(u):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40)
        return r.read().decode("utf-8", "replace"), r.geturl()
    except Exception as e:
        return None, str(e)
os.makedirs("out", exist_ok=True)
home, _ = get("https://www.mvr.bg/")
slugs = sorted(set(re.findall(r'href="(?:https://www\.mvr\.bg)?/([a-z\-]+)/?"', home or "")))
print("HOME SLUGS", slugs)
base = "/обществен-ред-и-сигурност/мвр-съветва/полезна-информация"
for s in slugs:
    u = "https://www.mvr.bg/" + s + urllib.parse.quote(base)
    t, fin = get(u)
    if not t:
        continue
    links = set()
    for href, txt in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', t, re.S):
        tx = html.unescape(re.sub(r"<[^>]+>", "", txt)).strip()
        if re.search(r"камер|скорост|АТСС|автоматизира", tx, re.I):
            links.add((urllib.parse.unquote(href), tx[:120]))
    print("REGION", s, "links:", len(links))
    for i, (h, tx) in enumerate(sorted(links)):
        print("  LINK", s, h, "|", tx)
        full = h if h.startswith("http") else "https://www.mvr.bg" + urllib.parse.quote(h)
        p, _ = get(full)
        if p:
            open(f"out/{s}_{i}.html", "w").write(p)
            for f in re.findall(r'href="([^"]+\.(?:pdf|xlsx?|docx?))"', p, re.I):
                print("    FILE", s, urllib.parse.unquote(f))
