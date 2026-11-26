"""단면도감 몰아보기(롱폼)를 유튜브에만 올린다. queue_long/<번호_이름>/ 하나가 한 편.

- 영상은 깃허브 한 파일 100MB 제한 때문에 video.mp4.part00, part01 ... 로 나눠 두고 여기서 이어 붙여요.
- after.txt(예: 2026-12-05)가 있으면 그 날(한국 시간) 전에는 안 올려요. 안에 든 쇼츠가 먼저 다 공개된 뒤 올리려고요.
- 롱폼이라 제목에 #shorts를 붙이지 않고, 비공개로 올린 뒤 10분 뒤 공개되게 예약해요(쇼츠와 같은 방식).
- thumb.jpg(1280x720) 썸네일, captions.en.srt 영어 자막, 첫 댓글('## 유튜브 댓글')을 넣어요.
"""
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QUEUE_DIR", "queue_long")
os.environ.setdefault("STATE_FILE", "posted_long.json")
import requests  # noqa: E402
import upload as up  # noqa: E402


def join_parts(item):
    video = item / "video.mp4"
    parts = sorted(item.glob("video.mp4.part*"))
    if parts and not video.exists():
        with video.open("wb") as f:
            for p in parts:
                f.write(p.read_bytes())
    return video


def youtube_long(item, copy):
    token = up.check(requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["YT_CLIENT_ID"],
        "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }))["access_token"]
    publish_at = os.environ.get("YT_PUBLISH_AT") or time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 60 * int(os.environ.get("YT_PUBLISH_DELAY_MIN", "10"))))
    status = {"privacyStatus": "private", "publishAt": publish_at,
              "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    if os.environ.get("YT_PRIVACY") in ("private", "unlisted"):
        status = {"privacyStatus": os.environ["YT_PRIVACY"], "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
        publish_at = None
    meta = {"snippet": {"title": copy["yt_title"].replace("#shorts", "").strip()[:100],
                        "description": copy["yt_desc"], "categoryId": "27", "defaultLanguage": "ko"},
            "status": status}
    video = join_parts(item)
    size = video.stat().st_size
    init = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)},
        data=json.dumps(meta),
    )
    up.check(init)
    with video.open("rb") as f:
        res = up.check(requests.put(init.headers["Location"], data=f,
                                    headers={"Authorization": f"Bearer {token}", "Content-Type": "video/mp4",
                                             "Content-Length": str(size)}))
    up.LAST_YT.update(id=res["id"], token=token, publish_at=publish_at)
    up.set_thumbnail(res["id"], token, item)
    up.set_captions(res["id"], token, item)
    return f"https://youtu.be/{res['id']}"


def main():
    state = up.load_state()
    today = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 9 * 3600))
    items = sorted(d for d in up.QUEUE.iterdir() if d.is_dir() and (d / "upload_copy.md").exists())
    only = os.environ.get("LONG_ITEM", "").strip()
    ready = []
    for d in items:
        if "youtube" in state.get(d.name, {}) or (only and d.name != only):
            continue
        after = (d / "after.txt").read_text().strip() if (d / "after.txt").exists() else ""
        if after and today < after and not only:
            print(f"{d.name}: {after}부터 올려요(오늘 {today})")
            continue
        ready.append(d)
    if not ready:
        print("지금 올릴 몰아보기가 없어요.")
        return 0
    item = ready[0]
    copy = up.parse_copy(item / "upload_copy.md")
    print(f"이번 편: {item.name}")
    try:
        link = youtube_long(item, copy)
    except Exception as e:
        print(f"유튜브: 실패 {e}")
        return 1
    state.setdefault(item.name, {})["youtube"] = link
    print(f"유튜브: 완료 {link}")
    up.save_state(state)
    if os.environ.get("TEST_RUN") != "true":
        cid = up.youtube_comment(item, copy)
        if cid:
            state[item.name]["youtube_comment"] = cid
            up.save_state(state)
        up.set_thumbnail(up.LAST_YT["id"], up.LAST_YT["token"], item)
    return 0


if __name__ == "__main__":
    sys.exit(main())
