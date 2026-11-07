param(
    [switch]$MigrateOnly,
    [switch]$SeedOnly,
    [ValidateRange(1, 65535)]
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

if ($MigrateOnly -and $SeedOnly) {
    throw "Use -MigrateOnly ou -SeedOnly, não os dois ao mesmo tempo."
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $projectRoot

$envFile = Join-Path $projectRoot ".env"
$localConfig = @{}
if (Test-Path -LiteralPath $envFile) {
    foreach ($line in Get-Content -LiteralPath $envFile) {
        if ($line -match '^\s*(DATABASE_URL|POSTGRES_USER|POSTGRES_PASSWORD|POSTGRES_DB|POSTGRES_PORT|APPRUNCLOUD_BASE_URL|APPRUNCLOUD_API_KEY|APPRUNCLOUD_ORG_ID|APPRUNCLOUD_TIMEOUT)\s*=\s*(.*?)\s*$') {
            $value = $Matches[2].Trim()
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            $localConfig[$Matches[1]] = $value
        }
    }
}

$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        throw "Python 3.12 não encontrado e .venv ainda não existe. Instale Python 3.12 e habilite 'Add Python to PATH'."
    }
    $systemPython = $python.Source
    $pythonVersion = & $systemPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ($LASTEXITCODE -ne 0 -or [version]$pythonVersion -lt [version]"3.12") {
        throw "O Olimpo requer Python 3.12 ou superior. Versão encontrada: $pythonVersion"
    }

    & $systemPython -m venv (Join-Path $projectRoot ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Não foi possível criar o ambiente Python." }
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Não foi possível atualizar o pip." }
    & $venvPython -m pip install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) { throw "Não foi possível instalar as dependências Python." }
}

$pythonVersion = & $venvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0 -or [version]$pythonVersion -lt [version]"3.12") {
    throw "O ambiente .venv requer Python 3.12 ou superior. Versão encontrada: $pythonVersion"
}

# Este modo inicia só a API para desenvolvimento visual. Ele sempre aponta
# para serviços locais e mantém toda execução externa desativada.
$env:PYTHONPATH = Join-Path $projectRoot "src"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:OLIMPO_ENV = "development"
$env:DISPATCH_ENABLED = "false"
$env:GLOBAL_KILL_SWITCH = "true"
$env:INSTAGRAM_PROVIDER = "legacy"
if (-not $env:DATABASE_URL) {
    if ($localConfig.ContainsKey("DATABASE_URL")) {
        $env:DATABASE_URL = $localConfig["DATABASE_URL"]
    } else {
        $dbUser = if ($localConfig.ContainsKey("POSTGRES_USER")) { $localConfig["POSTGRES_USER"] } else { "olimpo" }
        $dbPassword = if ($localConfig.ContainsKey("POSTGRES_PASSWORD")) { $localConfig["POSTGRES_PASSWORD"] } else { "olimpo" }
        $dbName = if ($localConfig.ContainsKey("POSTGRES_DB")) { $localConfig["POSTGRES_DB"] } else { "olimpo" }
        $dbPort = if ($localConfig.ContainsKey("POSTGRES_PORT")) { $localConfig["POSTGRES_PORT"] } else { "55432" }
        $escapedUser = [Uri]::EscapeDataString($dbUser)
        $escapedPassword = [Uri]::EscapeDataString($dbPassword)
        $escapedDbName = [Uri]::EscapeDataString($dbName)
        $env:DATABASE_URL = "postgresql+asyncpg://${escapedUser}:${escapedPassword}@127.0.0.1:${dbPort}/${escapedDbName}"
    }
}
try {
    $databaseUri = [Uri]$env:DATABASE_URL
} catch {
    throw "DATABASE_URL inválida. Informe uma conexão PostgreSQL local no formato postgresql+asyncpg://usuario:senha@127.0.0.1:55432/olimpo."
}
if ($databaseUri.Host -notin @("localhost", "127.0.0.1", "::1")) {
    throw "O runner local só aceita PostgreSQL neste computador. Não será usado DATABASE_URL remoto."
}
$databasePort = $databaseUri.Port
if ($databasePort -lt 1) {
    $databasePort = 5432
}
$databaseReachable = Test-NetConnection -ComputerName $databaseUri.Host -Port $databasePort `
    -InformationLevel Quiet -WarningAction SilentlyContinue
if (-not $databaseReachable) {
    throw "PostgreSQL local indisponível em $($databaseUri.Host):$databasePort. Abra o Docker Desktop, aguarde o mecanismo iniciar e rode 'docker compose up -d postgres'."
}
$env:DATABASE_POOL_SIZE = "4"
$env:DATABASE_MAX_OVERFLOW = "2"
$env:REDIS_URL = "redis://127.0.0.1:6379/0"
$env:LLM_GATEWAY_URL = "http://127.0.0.1:4000"
$env:DRYRUN_DIR = Join-Path $projectRoot "runtime\dryrun"
$env:MEDIA_ROOT = Join-Path $projectRoot "runtime\media"

# Carrega da configuração local apenas as credenciais necessárias para a
# consulta de inventário (GET). Nenhuma chave de geração ou serviço de ação é
# habilitada por este script.
foreach ($name in @("APPRUNCLOUD_BASE_URL", "APPRUNCLOUD_API_KEY", "APPRUNCLOUD_ORG_ID", "APPRUNCLOUD_TIMEOUT")) {
    if ($localConfig.ContainsKey($name)) {
        [Environment]::SetEnvironmentVariable($name, $localConfig[$name], "Process")
    }
}

foreach ($name in @(
    "FAL_API_KEY", "OPENAI_IMAGE_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    "REPLICATE_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN",
    "LITELLM_MASTER_KEY", "ORCHESTRATOR_URL",
    "ORCHESTRATOR_TOKEN", "PERSONA_ENGINE_URL", "PERSONA_ENGINE_TOKEN",
    "ANDROID_MANAGER_URL", "ANDROID_MANAGER_TOKEN", "MEDIA_FORGE_URL",
    "MEDIA_FORGE_TOKEN"
)) {
    [Environment]::SetEnvironmentVariable($name, "", "Process")
}

New-Item -ItemType Directory -Force -Path $env:DRYRUN_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $env:MEDIA_ROOT | Out-Null
if ($MigrateOnly) {
    & $venvPython -m olimpo.db.migrate up
    exit $LASTEXITCODE
}
if ($SeedOnly) {
    & $venvPython -m olimpo.db.seed
    exit $LASTEXITCODE
}

$portProbe = $null
try {
    $portProbe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
    $portProbe.Start()
} catch [System.Net.Sockets.SocketException] {
    throw "A porta $Port já está ocupada. Escolha outra com -Port (por exemplo, -Port 8001)."
} finally {
    if ($portProbe) { $portProbe.Stop() }
}

Write-Host "Olimpo API local: http://127.0.0.1:$Port/docs"
Write-Host "Modo local isolado. PostgreSQL local precisa estar disponível; dispatch permanece desativado."

& $venvPython -m uvicorn olimpo.api.main:app --reload --host 127.0.0.1 --port $Port
exit $LASTEXITCODE

