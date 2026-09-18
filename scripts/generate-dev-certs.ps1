$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path "certs" | Out-Null
openssl req -x509 -newkey rsa:4096 -sha256 -days 30 -nodes `
  -keyout certs/privkey.pem -out certs/fullchain.pem `
  -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
Write-Host "Development certificate created in certs/. Do not use it in production."

