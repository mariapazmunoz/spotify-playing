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
        "image_url": song.get("album", {}).get("images", [{}])[0].get("url")
    }


@app.get("/api/spotify.svg")
def spotify_card():
    info = current_song()

    if info["is_playing"] is False:
        svg = """
        <svg width="450" height="120" xmlns="http://www.w3.org/2000/svg">
            <rect width="100%" height="100%" rx="18" fill="#121212"/>
            <text x="20" y="35" font-size="20" fill="#1DB954" font-family="Arial">
                Spotify
            </text>
            <text x="20" y="70" font-size="18" fill="white" font-family="Arial">
                Not playing anything right now
            </text>
        </svg>
        """
        return Response(content=svg, media_type="image/svg+xml")

    title = info["title"]
    artist = info["artist"]

    if len(title) > 30:
        title = title[:30] + "..."

    if len(artist) > 35:
        artist = artist[:35] + "..."

    svg = f"""
    <svg width="450" height="120" xmlns="http://www.w3.org/2000/svg">
        <rect width="100%" height="100%" rx="18" fill="#121212"/>
        <text x="20" y="35" font-size="20" fill="#1DB954" font-family="Arial">
            Spotify Now Playing
        </text>
        <text x="20" y="70" font-size="18" fill="white" font-family="Arial">
            {title}
        </text>
        <text x="20" y="95" font-size="14" fill="#b3b3b3" font-family="Arial">
            {artist}
        </text>
    </svg>
    """

    return Response(content=svg, media_type="image/svg+xml")
