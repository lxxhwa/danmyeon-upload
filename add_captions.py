"""이미 올라간 편에 쉬운 영어 자막(queue/<편>/captions.en.srt)을 붙인다. 인자: 폴더 이름들(쉼표), 비우면 전부.
이미 영어 자막이 있는 영상은 건너뛰어요(중복 방지)."""
import json, os, re, sys
from pathlib import Path
import requests
from upload import set_captions

state = json.loads(Path("posted.json").read_text())
token = requests.post("https://oauth2.googleapis.com/token", data={
    "client_id": os.environ["YT_CLIENT_ID"], "client_secret": os.environ["YT_CLIENT_SECRET"],
    "refresh_token": os.environ["YT_REFRESH_TOKEN"], "grant_type": "refresh_token"}).json()["access_token"]
names = [n.strip() for n in (sys.argv[1] if len(sys.argv) > 1 else "").split(",") if n.strip()] or sorted(state)
failed = False
for name in names:
    m = re.search(r"shorts/([\w-]{11})", state.get(name, {}).get("youtube", ""))
    if not m or not (Path("queue") / name / "captions.en.srt").exists():
        print(name, "건너뜀(유튜브에 안 올라갔거나 영어 자막 파일 없음)"); continue
    vid = m.group(1)
    have = requests.get("https://www.googleapis.com/youtube/v3/captions", params={"part": "snippet", "videoId": vid},
                        headers={"Authorization": f"Bearer {token}"}).json().get("items", [])
    if any(c["snippet"]["language"] == "en" and c["snippet"].get("trackKind") != "asr" for c in have):
        print(name, vid, "이미 영어 자막 있음"); continue
    print(name, vid)
    failed |= not set_captions(vid, token, Path("queue") / name)
sys.exit(1 if failed else 0)
