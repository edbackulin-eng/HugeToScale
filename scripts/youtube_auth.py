"""Authorise the Huge To Scale channel once, by hand, and store the token as a GitHub secret.

    python scripts/youtube_auth.py client_secret.json    # consent in the browser, pick the channel, shows its name and id
    python scripts/youtube_auth.py --check               # which channel the stored token opens
    python scripts/youtube_auth.py --store               # YT_TOKEN_JSON -> GitHub Secrets, channel id -> variable YT_CHANNEL_ID

client_secret.json is the Desktop OAuth client of Google Cloud project yt-factory-510411 (owner 18.11); it is git-ignored.
Scopes: youtube.upload (upload) + youtube.readonly (read the channel's full video list for the duplicate guard).
+ yt-analytics.readonly (views, % viewed, subscribers per Short for the report after 10 Shorts).
The token stays in youtube_token.json (git-ignored) and in the secret; it is never printed.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPO = "edbackulin-eng/HugeToScale"
TOKEN_FILE = ROOT / "youtube_token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly",
          "https://www.googleapis.com/auth/yt-analytics.readonly"]   # analytics: report after 10 Shorts (owner 19.11)


def authorize(client_secret):
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline",
                                  success_message="Done - close this tab and go back to Claude.")
    if not creds.refresh_token:
        raise SystemExit("Google returned no refresh token: remove the app at myaccount.google.com/permissions and retry")
    if not set(SCOPES) <= set(creds.scopes or []):
        raise SystemExit(f"not all permissions were granted: {sorted(creds.scopes or [])}")
    TOKEN_FILE.write_text(json.dumps({"refresh_token": creds.refresh_token, "client_id": creds.client_id,
                                      "client_secret": creds.client_secret, "token_uri": creds.token_uri,
                                      "scopes": SCOPES}), encoding="utf-8")


def show():
    from core import ytguard
    yt = ytguard.service_from_env(env="__NO_ENV__", token_file=TOKEN_FILE)
    ch = yt.channels().list(part="snippet,statistics", mine=True).execute()["items"][0]
    print(f"channel: {ch['snippet']['title']}")
    print(f"id:      {ch['id']}")
    print(f"handle:  {ch['snippet'].get('customUrl', '-')}")
    print(f"videos:  {ch['statistics'].get('videoCount')}")
    return ch


def main(argv):
    if "--store" in argv:
        ch = show()
        if "huge" not in ch["snippet"]["title"].lower():
            print("This is NOT Huge To Scale - not stored.")
            return 1
        subprocess.run(["gh", "secret", "set", "YT_TOKEN_JSON", "--repo", REPO],
                       input=TOKEN_FILE.read_text(encoding="utf-8"), text=True, check=True)
        subprocess.run(["gh", "variable", "set", "YT_CHANNEL_ID", "--repo", REPO, "--body", ch["id"]], check=True)
        print("YT_TOKEN_JSON (secret) and YT_CHANNEL_ID (variable) stored in", REPO)
        return 0
    if "--check" in argv:
        show()
        return 0
    authorize(Path(argv[0]))
    show()
    print("If this is Huge To Scale:  python scripts/youtube_auth.py --store")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
