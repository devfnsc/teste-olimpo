param(
    [ValidateRange(1, 65535)]
    [int]$Port = 3000
)

$ErrorActionPreference = "Stop"

$panelRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\panel")).Path
Set-Location $panelRoot

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js 20 ou superior não encontrado. Instale Node.js e abra um novo PowerShell."
}

$nodeMajor = [int]((& node -p "process.versions.node.split('.')[0]").Trim())
if ($LASTEXITCODE -ne 0 -or $nodeMajor -lt 20) {
    throw "O painel requer Node.js 20 ou superior."
}

if (-not (Test-Path (Join-Path $panelRoot "node_modules"))) {
    if (-not (Test-Path (Join-Path $panelRoot "package-lock.json"))) {
        throw "package-lock.json não encontrado; restaure o lockfile antes de instalar o painel."
    }
    & npm ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw "Não foi possível instalar as dependências do painel." }
}

$rootEnvFile = Join-Path $panelRoot "..\.env"
if (-not $env:OLIMPO_API_URL -and (Test-Path $rootEnvFile)) {
    foreach ($line in Get-Content -LiteralPath $rootEnvFile) {
        if ($line -match '^\s*OLIMPO_API_URL\s*=\s*(.*?)\s*$') {
            $env:OLIMPO_API_URL = $Matches[1].Trim().Trim('"').Trim("'")
            break
        }
    }
}
if (-not $env:OLIMPO_API_URL) {
    $env:OLIMPO_API_URL = "http://127.0.0.1:8000"
}
try {
    $apiUri = [Uri]$env:OLIMPO_API_URL
} catch {
    throw "OLIMPO_API_URL inválida. O painel local deve apontar para http://127.0.0.1:8000."
}
if ($apiUri.Scheme -ne "http" -or $apiUri.Host -notin @("localhost", "127.0.0.1", "::1", "[::1]") -or
    $apiUri.UserInfo -or $apiUri.Query -or $apiUri.Fragment -or $apiUri.AbsolutePath -ne "/") {
    throw "O runner local do painel só aceita a API neste computador; use http://127.0.0.1:8000."
}
if (-not $env:OLIMPO_API_TOKEN -and $env:API_TOKEN) {
    $env:OLIMPO_API_TOKEN = $env:API_TOKEN
}
if (-not $env:OLIMPO_API_TOKEN) {
    if (Test-Path $rootEnvFile) {
        foreach ($line in Get-Content -LiteralPath $rootEnvFile) {
            if ($line -match '^\s*API_TOKEN\s*=\s*(.*?)\s*$') {
                $value = $Matches[1].Trim()
                if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                    $value = $value.Substring(1, $value.Length - 2)
                }
                $env:OLIMPO_API_TOKEN = $value
                break
            }
        }
    }
}

$portProbe = $null
try {
    $portProbe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
    $portProbe.Start()
} catch [System.Net.Sockets.SocketException] {
    throw "A porta $Port já está ocupada. Escolha outra com -Port (por exemplo, -Port 3001)."
} finally {
    if ($portProbe) { $portProbe.Stop() }
}

Write-Host "Olimpo Painel: http://127.0.0.1:$Port"
Write-Host "API configurada: $env:OLIMPO_API_URL"
& npm run dev -- --hostname 127.0.0.1 --port $Port
exit $LASTEXITCODE

