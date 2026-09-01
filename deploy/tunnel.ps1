# Open the panel on this machine, through SSH.
#
#     .\deploy\tunnel.ps1
#     then open http://localhost:8080
#
# Ports 80 and 443 on the VPS are blocked by the provider's network firewall —
# above the server, so nothing inside it can change that. Port 22 is open, and
# SSH will happily carry HTTP for us until the provider firewall is opened.
#
# This is not a workaround to keep. It is single-user, it dies with the
# terminal, and a customer cannot use it. It exists so the panel is usable
# while the firewall is being sorted out.
#
# Stop it with Ctrl+C.

$ErrorActionPreference = 'Stop'

$Remote  = 'root@187.77.141.155'
$Key     = "$HOME\.ssh\id_ed25519"
$Local   = 8080
$Target  = '127.0.0.1:8000'   # uvicorn, inside the container's published port

if (-not (Test-Path $Key)) {
    Write-Error "No SSH key at $Key"
}

Write-Host ""
Write-Host "  Tunnelling  localhost:$Local  ->  $Remote  ->  $Target" -ForegroundColor Cyan
Write-Host "  Open        http://localhost:$Local" -ForegroundColor Green
Write-Host "  Stop        Ctrl+C"
Write-Host ""

# -N: no remote command, just forward. The container publishes 8000 on the
# VPS loopback, so the far end of the tunnel is the loopback there.
ssh -N -L "${Local}:${Target}" -i $Key `
    -o ExitOnForwardFailure=yes `
    -o ServerAliveInterval=30 `
    $Remote
