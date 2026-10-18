import json
import os
import secrets
import threading
import webbrowser
from pathlib import Path

import requests
from flask import Flask, jsonify, redirect, render_template, request, session
from google.auth.exceptions import RefreshError
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

BASE_DIR = Path(__file__).resolve().parent
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "http://127.0.0.1:5000/oauth2callback")
CREDENTIALS_FILE = os.getenv("GOOGLE_CLIENT_SECRET_FILE", str(BASE_DIR / "client_secret.json"))

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))

OAUTH_PROVIDERS = {
    "github": {
        "authorize": "https://github.com/login/oauth/authorize",
        "token": "https://github.com/login/oauth/access_token",
        "profile": "https://api.github.com/user",
        "scope": "read:user user:email",
    },
    "discord": {
        "authorize": "https://discord.com/oauth2/authorize",
        "token": "https://discord.com/api/oauth2/token",
        "profile": "https://discord.com/api/users/@me",
        "scope": "identify email",
    },
    "microsoft": {
        "authorize": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "profile": "https://graph.microsoft.com/v1.0/me",
        "scope": "openid profile email User.Read",
    },
    "spotify": {
        "authorize": "https://accounts.spotify.com/authorize",
        "token": "https://accounts.spotify.com/api/token",
        "profile": "https://api.spotify.com/v1/me",
        "scope": "user-read-email",
    },
}


def credentials_path() -> Path:
    return Path(CREDENTIALS_FILE).expanduser()


def make_flow() -> Flow:
    path = credentials_path()
    if not path.is_file():
        raise FileNotFoundError(
            "Credenciais Google não configuradas. Defina GOOGLE_CLIENT_SECRET_FILE "
            "apontando para o JSON baixado do Google Cloud."
        )
    flow = Flow.from_client_secrets_file(str(path), scopes=SCOPES)
    flow.redirect_uri = REDIRECT_URI
    return flow


def error_response(message: str, status_code: int = 503):
    return jsonify({"ok": False, "error": message}), status_code


@app.get("/")
def index():
    return render_template("index.html", configured=credentials_path().is_file())


@app.get("/auth")
def auth():
    try:
        flow = make_flow()
    except FileNotFoundError as error:
        return error_response(str(error))
    authorization_url, state = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent"
    )
    session["state"] = state
    return redirect(authorization_url)


@app.get("/oauth2callback")
def oauth2callback():
    returned_state = request.args.get("state")
    if not returned_state or returned_state != session.get("state"):
        return error_response("Estado OAuth ausente ou inválido; tente conectar novamente.", 400)
    try:
        flow = make_flow()
        flow.fetch_token(authorization_response=request.url)
    except FileNotFoundError as error:
        return error_response(str(error))
    except Exception as error:  # Provedores OAuth usam exceções diferentes.
        app.logger.warning("Falha no callback OAuth: %s", type(error).__name__)
        return error_response(
            "A autorização foi recusada ou o token é inválido. Verifique o redirect URI e tente novamente.",
            401,
        )
    session["credentials"] = flow.credentials.to_json()
    session.pop("state", None)
    return redirect("/")


def gmail_service():
    raw = session.get("credentials")
    if not raw:
        return None
    credentials = Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
    return build("gmail", "v1", credentials=credentials)


def provider_config(provider: str):
    definition = OAUTH_PROVIDERS.get(provider)
    if not definition:
        return None, "Provedor não suportado."
    prefix = f"OAUTH_{provider.upper()}_"
    client_id = os.getenv(prefix + "CLIENT_ID")
    client_secret = os.getenv(prefix + "CLIENT_SECRET")
    if not client_id or not client_secret:
        return None, f"Defina {prefix}CLIENT_ID e {prefix}CLIENT_SECRET localmente."
    return {
        **definition,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect": f"http://127.0.0.1:5000/oauth2callback/{provider}",
    }, None


@app.get("/api/providers")
def providers():
    result = []
    for name in OAUTH_PROVIDERS:
        config, _ = provider_config(name)
        result.append({"name": name, "configured": config is not None})
    result.append({"name": "google-gmail", "configured": credentials_path().is_file()})
    return jsonify({"ok": True, "providers": result})


@app.get("/auth/<provider>")
def provider_auth(provider):
    config, error = provider_config(provider)
    if error:
        return error_response(error)
    state = secrets.token_urlsafe(32)
    session[f"oauth_state_{provider}"] = state
    params = {
        "client_id": config["client_id"],
        "redirect_uri": config["redirect"],
        "response_type": "code",
        "scope": config["scope"],
        "state": state,
    }
    query = requests.Request("GET", config["authorize"], params=params).prepare().url
    return redirect(query)


@app.get("/oauth2callback/<provider>")
def provider_callback(provider):
    config, error = provider_config(provider)
    if error:
        return error_response(error)
    if request.args.get("state") != session.get(f"oauth_state_{provider}"):
        return error_response("Estado OAuth ausente ou inválido; tente conectar novamente.", 400)
    if request.args.get("error"):
        return error_response("A autorização foi recusada pelo provedor.", 401)
    try:
        response = requests.post(
            config["token"],
            data={
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "code": request.args["code"],
                "redirect_uri": config["redirect"],
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
            timeout=15,
        )
        response.raise_for_status()
        token = response.json().get("access_token")
        if not token:
            return error_response("O provedor não retornou um access token.", 401)
        session[f"token_{provider}"] = token
        session.pop(f"oauth_state_{provider}", None)
        return redirect("/")
    except (requests.RequestException, ValueError):
        return error_response("Falha ao trocar o código OAuth por token.", 502)


@app.get("/api/status/<provider>")
def provider_status(provider):
    config, error = provider_config(provider)
    if error:
        return error_response(error)
    token = session.get(f"token_{provider}")
    if not token:
        return jsonify({"ok": True, "provider": provider, "configured": True, "connected": False})
    try:
        response = requests.get(
            config["profile"], headers={"Authorization": f"Bearer {token}"}, timeout=15
        )
        if response.status_code in (401, 403):
            session.pop(f"token_{provider}", None)
            return error_response("Token ausente, expirado ou sem permissão.", response.status_code)
        response.raise_for_status()
        profile = response.json()
        return jsonify({"ok": True, "provider": provider, "connected": True, "profile": profile})
    except (requests.RequestException, ValueError):
        return error_response("Falha ao consultar a API do provedor.", 502)


@app.get("/api/status")
def status():
    if not credentials_path().is_file():
        return jsonify({
            "ok": True,
            "configured": False,
            "connected": False,
            "message": "Defina GOOGLE_CLIENT_SECRET_FILE para habilitar o OAuth.",
        })
    try:
        service = gmail_service()
        if not service:
            return jsonify({"ok": True, "configured": True, "connected": False})
        profile = service.users().getProfile(userId="me").execute()
        return jsonify({
            "ok": True,
            "configured": True,
            "connected": True,
            "email": profile.get("emailAddress"),
            "messages": profile.get("messagesTotal", 0),
        })
    except (RefreshError, HttpError, ValueError, json.JSONDecodeError):
        session.pop("credentials", None)
        return error_response("Token ausente, expirado ou inválido. Conecte novamente.", 401)


if __name__ == "__main__":
    if os.getenv("OAUTH_OPEN_BROWSER", "1") == "1":
        threading.Timer(1.0, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
