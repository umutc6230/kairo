# Portable paket smoke testi: Kairo.exe sunucu modunda acilir, ana sayfa 200 donmeli.
# Gecici veri klasoru kullanir; kullanicinin data\ klasorune dokunmaz.
# Basarida dist\Kairo\SHA256.txt yazilir. Kullanim: powershell -File paketleme\smoke.ps1 [paket_klasoru]
param([string]$Paket = (Join-Path $PSScriptRoot "..\dist\Kairo"))
$ErrorActionPreference = "Stop"
$exe = Join-Path $Paket "Kairo.exe"
if (-not (Test-Path $exe)) { Write-Error "Kairo.exe bulunamadi: $exe"; exit 2 }

$dinleyici = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
$dinleyici.Start(); $port = $dinleyici.LocalEndpoint.Port; $dinleyici.Stop()
$veri = Join-Path ([System.IO.Path]::GetTempPath()) ("kairo-smoke-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $veri | Out-Null
$env:YAS_VERI_DIZINI = $veri

$surec = Start-Process -FilePath $exe -ArgumentList "--sunucu", "--port", $port -PassThru -WindowStyle Hidden
$tamam = $false
try {
    for ($i = 0; $i -lt 60 -and -not $surec.HasExited; $i++) {
        try {
            $y = Invoke-WebRequest -Uri "http://127.0.0.1:$port/" -UseBasicParsing -TimeoutSec 2
            if ($y.StatusCode -eq 200 -and $y.Content -match "Kairo") { $tamam = $true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
} finally {
    if (-not $surec.HasExited) { Stop-Process -Id $surec.Id -Force }
    Remove-Item -Recurse -Force $veri -ErrorAction SilentlyContinue
}
if (-not $tamam) { Write-Error "Smoke BASARISIZ: http://127.0.0.1:$port/ yanit vermedi"; exit 1 }

$hash = (Get-FileHash -Algorithm SHA256 $exe).Hash
"$hash  Kairo.exe" | Out-File -Encoding ascii (Join-Path $Paket "SHA256.txt")
Write-Output "Smoke GECTI (port $port). SHA256: $hash"
