"""유튜브 최근 편의 썸네일·숫자·공개 상태를 읽기만 한다. 썸네일 그림은 out/ 에 저장."""
import json, os, re, requests, pathlib
out = pathlib.Path("out"); out.mkdir(exist_ok=True)
S = json.load(open("posted.json"))
at = requests.post("https://oauth2.googleapis.com/token", data={"client_id": os.environ["YT_CLIENT_ID"], "client_secret": os.environ["YT_CLIENT_SECRET"], "refresh_token": os.environ["YT_REFRESH_TOKEN"], "grant_type": "refresh_token"}).json()
print("scope:", at.get("scope"))
H = {"Authorization": f"Bearer {at['access_token']}"}
ch = requests.get("https://www.googleapis.com/youtube/v3/channels", params={"part": "status,brandingSettings,snippet", "mine": "true"}, headers=H).json()
for c in ch.get("items", []): print("채널", c["snippet"]["title"], json.dumps(c.get("status"), ensure_ascii=False))
ids = {k: m.group(1) for k, v in S.items() if (m := re.search(r"(?:shorts/|v=|be/)([\w-]{11})", str(v.get("youtube", ""))))}
name = {i: k for k, i in ids.items()}
v = requests.get("https://www.googleapis.com/youtube/v3/videos", params={"part": "statistics,snippet,status,contentDetails", "id": ",".join(list(ids.values())[-16:])}, headers=H).json()
for it in v.get("items", []):
    s, sn, st = it["statistics"], it["snippet"], it["status"]
    th = sn["thumbnails"]
    print(name[it["id"]], it["id"], sn["publishedAt"], "조회", s.get("viewCount"), "좋아요", s.get("likeCount"), "| 공개", st.get("privacyStatus"), "| 썸네일 종류", list(th), "| 길이", it["contentDetails"]["duration"])
    for key in ["maxres", "high"]:
        if key in th:
            open(out / f"{name[it['id']]}_{key}.jpg", "wb").write(requests.get(th[key]["url"]).content); break
    for nm in ["oardefault", "oar2"]:
        r = requests.get(f"https://i.ytimg.com/vi/{it['id']}/{nm}.jpg")
        print("   ", nm, r.status_code, len(r.content))
        if r.ok: open(out / f"{name[it['id']]}_{nm}.jpg", "wb").write(r.content)
