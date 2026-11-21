"""지정한 편의 유튜브 썸네일을 영상 첫 장면(훅 문구 화면)으로 바꾼다. 인자: 폴더이름들(쉼표)."""
import json, os, re, sys, subprocess, requests
S = json.load(open("posted.json"))
at = requests.post("https://oauth2.googleapis.com/token", data={"client_id": os.environ["YT_CLIENT_ID"], "client_secret": os.environ["YT_CLIENT_SECRET"], "refresh_token": os.environ["YT_REFRESH_TOKEN"], "grant_type": "refresh_token"}).json()
H = {"Authorization": f"Bearer {at['access_token']}"}
for name in sys.argv[1].split(","):
    vid = re.search(r"shorts/([\w-]{11})", S[name]["youtube"]).group(1)
    jpg = f"/tmp/{name}.jpg"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", "0.1", "-i", f"queue/{name}/video.mp4", "-frames:v", "1", "-q:v", "3", jpg], check=True)
    r = requests.post(f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}", headers={**H, "Content-Type": "image/jpeg"}, data=open(jpg, "rb").read())
    print(name, vid, r.status_code, r.text[:400])
