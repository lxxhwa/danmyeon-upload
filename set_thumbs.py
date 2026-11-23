"""이미 올라간 편의 유튜브 썸네일을 queue/<편>/thumb.jpg(첫 장면)로 바꾼다. 인자: 폴더 이름들(쉼표)."""
import json, os, re, sys
from pathlib import Path
import requests
from upload import set_thumbnail

state = json.loads(Path("posted.json").read_text())
token = requests.post("https://oauth2.googleapis.com/token", data={
    "client_id": os.environ["YT_CLIENT_ID"], "client_secret": os.environ["YT_CLIENT_SECRET"],
    "refresh_token": os.environ["YT_REFRESH_TOKEN"], "grant_type": "refresh_token"}).json()["access_token"]
failed = False
for name in [n.strip() for n in sys.argv[1].split(",") if n.strip()]:
    m = re.search(r"shorts/([\w-]{11})", state.get(name, {}).get("youtube", ""))
    if not m:
        print(name, "아직 유튜브에 안 올라갔어요"); continue
    print(name, m.group(1))
    failed |= not set_thumbnail(m.group(1), token, Path("queue") / name)
sys.exit(1 if failed else 0)
