"""유튜브 공개 페이지에서 영상 상태(가족 친화, 제한, 길이 등)를 읽어 비교한다. 읽기만 한다."""
import json, re, sys, requests
H = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR"}
ids = [i for i in sys.argv[1].split(",") if i]
ch = requests.get("https://www.youtube.com/@danmyeon_dogam/shorts", headers=H).text
found = list(dict.fromkeys(re.findall(r'"videoId":"([\w-]{11})"', ch)))
print("채널 쇼츠 목록:", found)
for vid in dict.fromkeys(ids + found):
    t = requests.get(f"https://www.youtube.com/watch?v={vid}", headers=H).text
    m = re.search(r"ytInitialPlayerResponse\s*=\s*(\{.+?\});", t)
    if not m:
        print(vid, "플레이어 정보 없음"); continue
    p = json.loads(m.group(1))
    vd, mf = p.get("videoDetails", {}), p.get("microformat", {}).get("playerMicroformatRenderer", {})
    ps = p.get("playabilityStatus", {})
    print(json.dumps({
        "id": vid, "title": vd.get("title"), "length": vd.get("lengthSeconds"),
        "playable": ps.get("status"), "reason": ps.get("reason"),
        "familySafe": mf.get("isFamilySafe"), "unlisted": mf.get("isUnlisted"), "category": mf.get("category"),
        "w": mf.get("embed", {}).get("width"), "h": mf.get("embed", {}).get("height"),
        "publish": mf.get("publishDate"), "upload": mf.get("uploadDate"),
        "countries": len(mf.get("availableCountries", []) or []), "isShortsEligible": mf.get("isShortsEligible"),
        "private": vd.get("isPrivate"), "crawlable": vd.get("isCrawlable"), "liveContent": vd.get("isLiveContent"),
        "views": vd.get("viewCount"), "keywords": vd.get("keywords"),
    }, ensure_ascii=False))
