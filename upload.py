"""단면도감 자동 업로드: queue/ 에서 아직 안 올린 편 하나를 골라 유튜브·인스타·스레드에 올린다.

queue/<번호_이름>/video.mp4 와 upload_copy.md 가 한 편이다. 올린 결과는 posted.json 에 남긴다.
플랫폼 하나가 실패하면 그 플랫폼만 다음 실행 때 다시 시도한다.
"""
import calendar
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent
# 채널마다 대기열과 기록을 따로 둬요. 단면도감은 queue/ + posted.json, 만약도감은 queue_manyak/ + posted_manyak.json.
QUEUE = ROOT / os.environ.get("QUEUE_DIR", "queue")
STATE = ROOT / os.environ.get("STATE_FILE", "posted.json")
PLATFORMS = ["youtube", "instagram", "threads"]
# 대기 중인 편이 이만큼 이상이면 매일, 아니면 월·수·금에만 올린다.
DAILY_FROM = int(os.environ.get("DAILY_FROM", "7"))
AI_NOTE = "\n\n🤖 AI로 만든 영상이에요."
# 유튜브에 올린 뒤 채널 이름으로 다는 첫 댓글. upload_copy.md 에 '## 유튜브 댓글' 칸이 있으면 그걸 써요.
# 고정은 API로 안 돼서 앱이나 스튜디오에서 직접 눌러야 해요.
YT_COMMENTS = {
    "queue": (
        "봐주셔서 감사합니다 🔍\n"
        "겉으로는 절대 볼 수 없는 곳을 3D로 반 갈라 보여드려요.\n"
        "재밌으셨다면 구독하고 매일 저녁 6시, 다음 단면도 같이 봐요!\n\n"
        "다음엔 어디를 잘라볼까요? 궁금한 곳을 답글로 남겨주세요 👇"
    ),
    "queue_manyak": (
        "봐주셔서 감사합니다 🌍\n"
        "말도 안 되는 '만약에'를 과학으로 끝까지 따라가 보는 채널이에요.\n"
        "재밌으셨다면 구독하고 매일 저녁 6시, 다음 만약도 같이 봐요!\n\n"
        "궁금한 '만약에'가 있으면 답글로 남겨주세요 👇"
    ),
}
LAST_YT = {}


def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save_state(state):
    if os.environ.get("TEST_RUN") == "true":
        return
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
    yt = next(("\n".join(v).strip() for k, v in sections.items() if k.startswith("유튜브") and "댓글" not in k), "")
    m = re.search(r"^제목:\s*(.+)$", yt, re.M)
    desc = yt.split("설명:", 1)[1].strip() if "설명:" in yt else ""
    return {
        "yt_title": m.group(1).strip() if m else "",
        "yt_desc": desc,
        "instagram": get("인스타"),
        "threads": get("스레드"),
        "yt_comment": get("유튜브 댓글"),
    }


def public_video_url(item):
    repo = os.environ["GITHUB_REPOSITORY"]
    ref = os.environ.get("GITHUB_SHA", "main")
    return f"https://raw.githubusercontent.com/{repo}/{ref}/{QUEUE.name}/{item.name}/video.mp4"


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
    title = copy["yt_title"]
    if "#shorts" not in title.lower():
        title = f"{title} #shorts"
    status = {
        "privacyStatus": os.environ.get("YT_PRIVACY", "public"),
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": True,
    }
    # 예약 공개: 비공개로 미리 올려 두면 이 시각(UTC, 예: 2026-11-02T09:00:00Z)에 유튜브가 공개로 바꿔요.
    publish_at = os.environ.get("YT_PUBLISH_AT")
    # 바로 공개로 올리면 쇼츠 피드에 안 뜬 적이 있어서, 비공개로 올리고 몇 분 뒤 공개되게 예약할 수 있어요.
    if not publish_at and os.environ.get("YT_PUBLISH_DELAY_MIN"):
        publish_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 60 * int(os.environ["YT_PUBLISH_DELAY_MIN"])))
    if publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at
    meta = {
        "snippet": {"title": title[:100], "description": copy["yt_desc"], "categoryId": "27"},
        "status": status,
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
    LAST_YT.update(id=res["id"], token=token, publish_at=publish_at)
    return f"https://youtube.com/shorts/{res['id']}"


def youtube_comment(item, copy):
    """방금 올린 영상에 첫 댓글을 단다. 비공개일 땐 댓글이 안 달려서 공개 시각까지 기다린다."""
    text = copy.get("yt_comment") or YT_COMMENTS.get(QUEUE.name, "")
    if not text or not LAST_YT:
        return None
    if LAST_YT.get("publish_at"):
        due = calendar.timegm(time.strptime(LAST_YT["publish_at"], "%Y-%m-%dT%H:%M:%SZ"))
        wait = due - time.time() + 60
        if wait > 3600:
            print(f"  댓글: 공개가 {int(wait // 60)}분 뒤라 이번엔 건너뛰어요.")
            return None
        if wait > 0:
            print(f"  댓글: 공개될 때까지 {int(wait)}초 기다려요.")
            time.sleep(wait)
    body = {"snippet": {"videoId": LAST_YT["id"], "topLevelComment": {"snippet": {"textOriginal": text}}}}
    last = ""
    for i in range(4):
        r = requests.post("https://www.googleapis.com/youtube/v3/commentThreads?part=snippet",
                          headers={"Authorization": f"Bearer {LAST_YT['token']}"}, json=body)
        if r.ok:
            return r.json()["id"]
        last = f"{r.status_code} {r.text[:300]}"
        if r.status_code in (401, 403) and "insufficient" in r.text.lower():
            break  # 토큰에 댓글 권한(youtube.force-ssl)이 없어요.
        time.sleep(60 * (i + 1))
    print(f"  댓글: 실패 {last}")
    return None


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
    uid, tok = os.environ.get("THREADS_USER_ID") or "me", os.environ["THREADS_TOKEN"]
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
    waiting = sum(1 for d in items if any(p not in state.get(d.name, {}) for p in wanted))
    today = time.gmtime(time.time() + 9 * 3600).tm_wday  # 한국 시간 요일, 월=0
    if os.environ.get("SCHEDULED") == "true" and today not in (0, 2, 4) and waiting < DAILY_FROM:
        print(f"오늘은 쉬는 날이에요. 대기 {waiting}편 (매일 올리기는 {DAILY_FROM}편부터)")
        return 0
    print(f"대기 중인 편: {waiting}편")
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
    if LAST_YT and os.environ.get("TEST_RUN") != "true":
        cid = youtube_comment(item, copy)  # 댓글이 실패해도 업로드는 성공으로 둬요.
        if cid:
            state.setdefault(item.name, {})["youtube_comment"] = cid
            print(f"  댓글: 완료 {cid}")
            save_state(state)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
