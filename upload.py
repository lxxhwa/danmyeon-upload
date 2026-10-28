"""단면도감 자동 업로드: queue/ 에서 아직 안 올린 편 하나를 골라 유튜브·인스타·스레드에 올린다.

queue/<번호_이름>/video.mp4 와 upload_copy.md 가 한 편이다. 올린 결과는 posted.json 에 남긴다.
플랫폼 하나가 실패하면 그 플랫폼만 다음 실행 때 다시 시도한다.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent
QUEUE = ROOT / "queue"
STATE = ROOT / "posted.json"
PLATFORMS = ["youtube", "instagram", "threads"]
AI_NOTE = "\n\n🤖 AI로 만든 영상이에요."


def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save_state(state):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")


def parse_copy(path):
    """upload_copy.md 의 '## 유튜브', '## 인스타', '## 스레드' 섹션을 읽는다."""
    sections, cur = {}, None
    for line in path.read_text().splitlines():
        if line.startswith("## "):
            cur = line[3:].strip()
            sections[cur] = []
        elif cur and not line.startswith("※"):
            sections[cur].append(line)
    get = lambda key: next(("\n".join(v).strip() for k, v in sections.items() if k.startswith(key)), "")
    yt = get("유튜브")
    m = re.search(r"^제목:\s*(.+)$", yt, re.M)
    desc = yt.split("설명:", 1)[1].strip() if "설명:" in yt else ""
    return {
        "yt_title": m.group(1).strip() if m else "",
        "yt_desc": desc,
        "instagram": get("인스타"),
        "threads": get("스레드"),
    }


def public_video_url(item):
    repo = os.environ["GITHUB_REPOSITORY"]
    ref = os.environ.get("GITHUB_SHA", "main")
    return f"https://raw.githubusercontent.com/{repo}/{ref}/queue/{item.name}/video.mp4"


def check(resp):
    if not resp.ok:
        raise RuntimeError(f"{resp.status_code} {resp.text[:500]}")
    return resp.json() if resp.content else {}


# ---------- 유튜브 ----------
def youtube(item, copy):
    token = check(requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["YT_CLIENT_ID"],
        "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }))["access_token"]
    meta = {
        "snippet": {"title": copy["yt_title"][:100], "description": copy["yt_desc"], "categoryId": "27"},
        "status": {
            "privacyStatus": os.environ.get("YT_PRIVACY", "public"),
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        },
    }
    video = (item / "video.mp4").read_bytes()
    init = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(len(video))},
        data=json.dumps(meta),
    )
    check(init)
    res = check(requests.put(init.headers["Location"], data=video,
                             headers={"Authorization": f"Bearer {token}", "Content-Type": "video/mp4"}))
    return f"https://youtube.com/shorts/{res['id']}"


# ---------- 인스타·스레드 공통: 컨테이너 만들고, 처리 끝나면 게시 ----------
def wait_ready(url, params, field, timeout=600):
    start = time.time()
    while time.time() - start < timeout:
        status = check(requests.get(url, params=params)).get(field)
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"처리 실패: {status}")
        time.sleep(15)
    raise RuntimeError("처리 시간 초과")


def instagram(item, copy):
    base = "https://graph.instagram.com"
    uid, tok = os.environ["IG_USER_ID"], os.environ["IG_TOKEN"]
    cid = check(requests.post(f"{base}/{uid}/media", data={
        "media_type": "REELS",
        "video_url": public_video_url(item),
        "caption": copy["instagram"],
        "share_to_feed": "true",
        "is_ai_generated": "true",
        "access_token": tok,
    }))["id"]
    wait_ready(f"{base}/{cid}", {"fields": "status_code", "access_token": tok}, "status_code")
    mid = check(requests.post(f"{base}/{uid}/media_publish", data={"creation_id": cid, "access_token": tok}))["id"]
    link = check(requests.get(f"{base}/{mid}", params={"fields": "permalink", "access_token": tok}))
    return link.get("permalink", mid)


def threads(item, copy):
    base = "https://graph.threads.net/v1.0"
    uid, tok = os.environ["THREADS_USER_ID"], os.environ["THREADS_TOKEN"]
    cid = check(requests.post(f"{base}/{uid}/threads", data={
        "media_type": "VIDEO",
        "video_url": public_video_url(item),
        "text": (copy["threads"] + AI_NOTE)[:500],
        "access_token": tok,
    }))["id"]
    wait_ready(f"{base}/{cid}", {"fields": "status", "access_token": tok}, "status")
    mid = check(requests.post(f"{base}/{uid}/threads_publish", data={"creation_id": cid, "access_token": tok}))["id"]
    link = check(requests.get(f"{base}/{mid}", params={"fields": "permalink", "access_token": tok}))
    return link.get("permalink", mid)


UPLOADERS = {"youtube": youtube, "instagram": instagram, "threads": threads}


def main():
    wanted = [p.strip() for p in os.environ.get("PLATFORMS", ",".join(PLATFORMS)).split(",") if p.strip()]
    state = load_state()
    items = sorted(d for d in QUEUE.iterdir() if (d / "video.mp4").exists())
    item = next((d for d in items if any(p not in state.get(d.name, {}) for p in wanted)), None)
    if not item:
        print("올릴 영상이 없어요. queue/ 에 다음 편을 넣어 주세요.")
        return 0
    copy = parse_copy(item / "upload_copy.md")
    print(f"이번 편: {item.name}")
    failed = False
    for p in wanted:
        if p in state.get(item.name, {}):
            continue
        try:
            link = UPLOADERS[p](item, copy)
            state.setdefault(item.name, {})[p] = link
            print(f"  {p}: 완료 {link}")
        except Exception as e:
            failed = True
            print(f"  {p}: 실패 {e}")
        save_state(state)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
