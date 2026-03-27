from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse, Response
from dotenv import load_dotenv
import os
import base64
import requests
from urllib.parse import urlencode

# .env loading 
load_dotenv()

app = FastAPI()

# Get spotify data located .env
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")

# Spotify's links
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
CURRENT_SONG_URL = "https://api.spotify.com/v1/me/player/currently-playing"

# tokens 
access_token = None
refresh_token = None

# Check
@app.get("/")
def home():
    return {"message": "My Spotify API is working"}


@app.get("/login")
def login():
    # Spotify permission
    scope = "user-read-currently-playing user-read-playback-state"

    # User to Spotify
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": scope
    }

    # url
    spotify_login_url = AUTH_URL + "?" + urlencode(params)

    return RedirectResponse(spotify_login_url)


@app.get("/callback")
def callback(code: str):
    global access_token, refresh_token

    # Codification (base64)
    text = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded_text = base64.b64encode(text.encode()).decode()

    headers = {
        "Authorization": f"Basic {encoded_text}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    body = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI
    }

    response = requests.post(TOKEN_URL, headers=headers, data=body)

    # In case of error
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    data = response.json()

    # Keep tokens
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")

    return {
        "message": "Spotify connected successfully",
        "access_token_saved": access_token is not None,
        "refresh_token_saved": refresh_token is not None
    }

# In case of token durations lasts more than 1 hour ()
# Ask again for the new token
def get_new_access_token():
    global access_token, refresh_token

    if refresh_token is None:
        raise HTTPException(status_code=401, detail="No refresh token saved")

    text = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded_text = base64.b64encode(text.encode()).decode()

    headers = {
        "Authorization": f"Basic {encoded_text}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    body = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }

    response = requests.post(TOKEN_URL, headers=headers, data=body)

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    data = response.json()
    access_token = data.get("access_token")

    return access_token


@app.get("/api/spotify")
def current_song():
    global access_token

    # Check existance
    if access_token is None:
        raise HTTPException(status_code=401, detail="First go to /login")

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    response = requests.get(CURRENT_SONG_URL, headers=headers)

    # Need new token?
    if response.status_code == 401:
        new_token = get_new_access_token()
        headers["Authorization"] = f"Bearer {new_token}"
        response = requests.get(CURRENT_SONG_URL, headers=headers)

    # Not playing songs
    if response.status_code == 204:
        return {
            "is_playing": False,
            "message": "Nothing is playing right now"
        }

    # Error 
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    data = response.json()
    song = data.get("item")

    if song is None:
        return {
            "is_playing": False,
            "message": "No song data found"
        }

    artists = song.get("artists", [])
    artist_names = []

    for artist in artists:
        artist_names.append(artist["name"])

    return {
        "is_playing": data.get("is_playing", False),
        "title": song.get("name", "Unknown title"),
        "artist": ", ".join(artist_names),
        "album": song.get("album", {}).get("name", "Unknown album"),
        "song_url": song.get("external_urls", {}).get("spotify"),
        "progress_ms": data.get("progress_ms", 0),
        "duration_ms": song.get("duration_ms", 1),
    }


@app.get("/api/spotify.svg")
def spotify_card():
    info = current_song()

    if info["is_playing"] is False:
        svg = """
        <svg width="980" height="340" viewBox="0 0 980 340" xmlns="http://www.w3.org/2000/svg">
            <rect x="10" y="10" width="960" height="320" rx="28" fill="#121212"/>
            <rect x="42" y="42" width="240" height="240" rx="12" fill="url(#coverGradient)"/>
            <defs>
                <linearGradient id="coverGradient" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0%" stop-color="#6E8BFF"/>
                    <stop offset="100%" stop-color="#7B4DCC"/>
                </linearGradient>
            </defs>
            <text x="315" y="110" font-size="34" font-weight="700" fill="#F5F5F5" font-family="Arial">
                Nothing is playing
            </text>
            <text x="315" y="160" font-size="22" fill="#B3B3B3" font-family="Arial">
                Open Spotify and play something ✨
            </text>
        </svg>
        """
        return Response(content=svg, media_type="image/svg+xml")

    title = info["title"]
    artist = info["artist"]
    progress_ms = info.get("progress_ms", 0)
    duration_ms = max(info.get("duration_ms", 1), 1)

    if len(title) > 24:
        title = title[:24] + "..."

    if len(artist) > 28:
        artist = artist[:28] + "..."

    progress_ratio = max(0, min(progress_ms / duration_ms, 1))
    progress_width = int(540 * progress_ratio)

    def ms_to_minsec(ms: int) -> str:
        seconds = max(ms // 1000, 0)
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}:{secs:02d}"

    current_time = ms_to_minsec(progress_ms)
    total_time = ms_to_minsec(duration_ms)

    svg = f"""
    <svg width="980" height="340" viewBox="0 0 980 340" xmlns="http://www.w3.org/2000/svg">
        <defs>
            <linearGradient id="coverGradient" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="#6E8BFF"/>
                <stop offset="100%" stop-color="#7B4DCC"/>
            </linearGradient>
        </defs>

        <rect x="10" y="10" width="960" height="320" rx="28" fill="#121212"/>

        <rect x="42" y="42" width="240" height="240" rx="12" fill="url(#coverGradient)"/>

        <text x="315" y="98" font-size="38" font-weight="700" fill="#F5F5F5" font-family="Arial">
            {title}
        </text>

        <text x="315" y="148" font-size="26" fill="#B3B3B3" font-family="Arial">
            {artist}
        </text>

        <circle cx="335" cy="198" r="18" fill="#1ED760"/>
        <text x="365" y="208" font-size="24" font-weight="700" fill="#1ED760" font-family="Arial">
            NOW PLAYING
        </text>

        <rect x="315" y="240" width="540" height="8" rx="4" fill="#4A4A4A"/>
        <rect x="315" y="240" width="{progress_width}" height="8" rx="4" fill="#1ED760"/>

        <text x="315" y="288" font-size="18" fill="#B3B3B3" font-family="Arial">
            {current_time}
        </text>

        <text x="855" y="288" text-anchor="end" font-size="18" fill="#B3B3B3" font-family="Arial">
            {total_time}
        </text>
    </svg>
    """

    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
