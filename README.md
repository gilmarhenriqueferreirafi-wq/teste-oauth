# Teste OAuth

Laboratório local para testar autenticação OAuth e chamadas básicas de APIs.
Ele indica quando faltam credenciais, quando o token está expirado e quando a API retorna erro.

Provedores incluídos: Google/Gmail, GitHub, Discord, Microsoft e Spotify.
Cada provedor usa credenciais e escopos próprios; o projeto não promete compatibilidade
automática com toda empresa existente.

## Configuração local

1. Crie um ambiente virtual e instale as dependências:

   ```powershell
   py -m venv .venv
   .\\.venv\\Scripts\\Activate.ps1
   pip install -r requirements.txt
   ```

2. Baixe um JSON de cliente OAuth no Google Cloud e mantenha-o fora do Git.

3. Aponte para o arquivo apenas na sessão local:

   ```powershell
   $env:GOOGLE_CLIENT_SECRET_FILE = 'C:\\caminho\\client_secret.json'
   ```

4. Execute `py app.py` e abra `http://127.0.0.1:5000`.

O redirect autorizado no Google Cloud deve ser `http://127.0.0.1:5000/oauth2callback`.

Para os demais provedores, cadastre o redirect correspondente:
`http://127.0.0.1:5000/oauth2callback/github`, `discord`, `microsoft` ou `spotify`.
Depois de configurar as variáveis do `.env.example`, use `/auth/<provedor>` e
`/api/status/<provedor>`.

## Teste rápido sem credenciais

Sem configurar o Google Cloud, `GET /api/status` responde com `configured: false`, em vez de quebrar com erro 500.

Nunca publique o JSON de credenciais, tokens, cookies ou arquivos `.env`.
