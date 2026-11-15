"""인스타 릴스·유튜브 쇼츠 편별 통계를 읽기만 한다."""
import json, os, re, requests
S = json.load(open("posted.json"))
uid, tok = os.environ["IG_USER_ID"], os.environ["IG_TOKEN"]
base = "https://graph.facebook.com/v21.0" if tok.startswith("EAA") else "https://graph.instagram.com"
r = requests.get(f"{base}/{uid}/media", params={"fields": "id,caption,permalink,timestamp,like_count,comments_count,media_product_type", "limit": 30, "access_token": tok}).json()
print("== 인스타")
for m in r.get("data", []) or [r]:
    if "id" not in m: print(m); break
    out = {"t": m.get("timestamp"), "cap": (m.get("caption") or "")[:30].replace("\n", " "), "like": m.get("like_count"), "cmt": m.get("comments_count")}
    for metrics in ["views,reach,saved,shares,total_interactions,ig_reels_avg_watch_time,ig_reels_video_view_total_time", "views,reach,saved,shares"]:
        i = requests.get(f"{base}/{m['id']}/insights", params={"metric": metrics, "access_token": tok}).json()
        if "data" in i:
            for d in i["data"]: out[d["name"]] = d["values"][0]["value"]
            break
        out["err"] = i.get("error", {}).get("message", "")[:120]
    print(json.dumps(out, ensure_ascii=False))
print("== 유튜브")
at = requests.post("https://oauth2.googleapis.com/token", data={"client_id": os.environ["YT_CLIENT_ID"], "client_secret": os.environ["YT_CLIENT_SECRET"], "refresh_token": os.environ["YT_REFRESH_TOKEN"], "grant_type": "refresh_token"}).json()
print("scope:", at.get("scope"))
H = {"Authorization": f"Bearer {at.get('access_token')}"}
ids = {k: m.group(1) for k, v in S.items() if (m := re.search(r"(?:shorts/|v=|be/)([\w-]{11})", str(v.get("youtube", ""))))}
v = requests.get("https://www.googleapis.com/youtube/v3/videos", params={"part": "statistics,snippet", "id": ",".join(list(ids.values())[-20:])}, headers=H).json()
name = {i: k for k, i in ids.items()}
for it in v.get("items", []) or [v]:
    if "id" not in it: print(it); break
    s = it["statistics"]; print(name[it["id"]], it["snippet"]["publishedAt"], "조회", s.get("viewCount"), "좋아요", s.get("likeCount"), it["snippet"]["title"][:30])
a = requests.get("https://youtubeanalytics.googleapis.com/v2/reports", params={"ids": "channel==MINE", "startDate": "2026-10-20", "endDate": "2026-11-16", "metrics": "views,averageViewDuration,averageViewPercentage,engagedViews", "dimensions": "video", "sort": "-views", "maxResults": 25}, headers=H).json()
for row in a.get("rows", []) or [a]: print("분석", [name.get(row[0], row[0])] + row[1:] if isinstance(row, list) else str(row)[:300])
