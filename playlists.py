"""유튜브 재생목록 맞추기: playlists.json 에 적힌 대로 재생목록을 만들고, 빠진 영상만 끝에 넣는다.

여러 번 돌려도 이미 들어간 영상은 다시 넣지 않는다. 업로드가 끝날 때마다 돌아서 새 편도 자동으로 들어간다.
만든 재생목록 아이디는 playlist_ids.json 에 남겨서, 재생목록 제목을 앱에서 바꿔도 새로 만들지 않는다.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent
QUEUE = ROOT / os.environ.get("QUEUE_DIR", "queue")
STATE = ROOT / os.environ.get("STATE_FILE", "posted.json")
IDS = ROOT / "playlist_ids.json"
API = "https://www.googleapis.com/youtube/v3"


def check(resp):
    if not resp.ok:
        raise RuntimeError(f"{resp.status_code} {resp.text[:500]}")
    return resp.json() if resp.content else {}


def norm(title):
    return re.sub(r"\s+", "", re.sub(r"#shorts", "", title, flags=re.I))


def yt_title(item):
    m = re.search(r"^제목:\s*(.+)$", (item / "upload_copy.md").read_text(), re.M)
    return m.group(1).strip() if m else ""


def main():
    token = check(requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["YT_CLIENT_ID"],
        "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }))["access_token"]
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {token}"

    def retry(fn, tries=8):
        # 막 만든 재생목록은 유튜브 쪽에 반영되기까지 잠깐 '없음(404)'으로 나와요. 조금 기다렸다 다시 해요.
        for i in range(tries):
            r = fn()
            if r.status_code != 404 or i == tries - 1:
                return check(r)
            time.sleep(10)

    def pages(url, params):
        params = dict(params, maxResults=50)
        while True:
            d = retry(lambda: s.get(url, params=params))
            yield from d.get("items", [])
            if not d.get("nextPageToken"):
                return
            params["pageToken"] = d["nextPageToken"]

    # 채널에 올라간 영상 (손으로 올린 편도 제목으로 찾으려고)
    ch = check(s.get(f"{API}/channels", params={"part": "contentDetails", "mine": "true"}))["items"][0]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    by_title = {}
    for it in pages(f"{API}/playlistItems", {"part": "snippet", "playlistId": uploads}):
        by_title.setdefault(norm(it["snippet"]["title"]), it["snippet"]["resourceId"]["videoId"])

    # 대기열 순서대로, 유튜브에 올라간 편의 영상 아이디
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    videos = {}
    for item in sorted(d for d in QUEUE.iterdir() if (d / "upload_copy.md").exists()):
        link = state.get(item.name, {}).get("youtube", "")
        m = re.search(r"shorts/([\w-]{11})", link)
        vid = m.group(1) if m else (by_title.get(norm(yt_title(item))) if link else None)
        if vid:
            videos[item.name] = vid
        elif link:
            print(f"  {item.name}: 올렸다고 적혀 있는데 채널에서 못 찾았어요 (건너뜀)")

    config = json.loads((ROOT / "playlists.json").read_text()).get(QUEUE.name, [])
    ids = json.loads(IDS.read_text()) if IDS.exists() else {}
    mine = {p["snippet"]["title"]: p["id"] for p in pages(f"{API}/playlists", {"part": "snippet", "mine": "true"})}
    added = 0
    for pl in config:
        key = f"{QUEUE.name}:{pl['key']}"
        pid = ids.get(key) or mine.get(pl["title"])
        fresh = False
        if not pid:  # 처음이면 새로 만들어요. 한 번 만든 건 아이디로 기억해서, 제목을 바꿔도 다시 안 만들어요
            fresh = True
            pid = check(s.post(f"{API}/playlists", params={"part": "snippet,status"}, json={
                "snippet": {"title": pl["title"], "description": pl.get("description", ""), "defaultLanguage": "ko"},
                "status": {"privacyStatus": "public"},
            }))["id"]
            ids[key] = pid
            IDS.write_text(json.dumps(ids, ensure_ascii=False, indent=2) + "\n")
            print(f"{pl['title']}: 재생목록 준비 https://www.youtube.com/playlist?list={pid}")
        have = set() if fresh else {it["snippet"]["resourceId"]["videoId"]
                for it in pages(f"{API}/playlistItems", {"part": "snippet", "playlistId": pid})}
        wanted = list(videos) if pl["items"] == "all" else [n for n in pl["items"] if n in videos]
        for name in wanted:
            if videos[name] in have:
                continue
            retry(lambda: s.post(f"{API}/playlistItems", params={"part": "snippet"}, json={
                "snippet": {"playlistId": pid, "resourceId": {"kind": "youtube#video", "videoId": videos[name]}},
            }))
            have.add(videos[name])
            added += 1
            print(f"  {pl['title']} ← {name}")
    print(f"끝: 새로 넣은 영상 {added}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
