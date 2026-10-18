"""Teste manual do fluxo OAuth do Gmail sem armazenar credenciais no código."""

import os
from pathlib import Path

from google.auth.exceptions import RefreshError
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

BASE_DIR = Path(__file__).resolve().parent
ARQUIVO_CREDENCIAIS = Path(os.getenv("GOOGLE_CLIENT_SECRET_FILE", str(BASE_DIR / "client_secret.json")))
ESCOPOS = ["https://www.googleapis.com/auth/gmail.readonly"]


def main():
    if not ARQUIVO_CREDENCIAIS.is_file():
        raise SystemExit(
            "Credenciais ausentes. Defina GOOGLE_CLIENT_SECRET_FILE com o caminho "
            "do JSON do Google Cloud; nunca coloque esse arquivo no Git."
        )
    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(ARQUIVO_CREDENCIAIS), ESCOPOS)
        credenciais = flow.run_local_server(host="127.0.0.1", bind_addr="127.0.0.1", port=0)
        gmail = build("gmail", "v1", credentials=credenciais)
        perfil = gmail.users().getProfile(userId="me").execute()
    except RefreshError as error:
        raise SystemExit("Token expirado ou inválido; autentique novamente.") from error
    except HttpError as error:
        raise SystemExit(f"A API do Gmail respondeu com erro HTTP {error.resp.status}.") from error
    except FileNotFoundError as error:
        raise SystemExit("Arquivo de credenciais não encontrado.") from error
    print("OAuth funcionando!")
    print("E-mail autenticado:", perfil.get("emailAddress", "indisponível"))
    print("Mensagens na conta:", perfil.get("messagesTotal", "indisponível"))


if __name__ == "__main__":
    main()
