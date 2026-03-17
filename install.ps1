#
# kanban-mcp install script (Windows PowerShell)
# Installs kanban-mcp (via pipx), chooses a database backend (SQLite by
# default, or MySQL/MariaDB), and runs kanban-setup.
#
# Interactive (default):
#   .\install.ps1
#   irm https://raw.githubusercontent.com/.../install.ps1 | iex
#
# Non-interactive:
#   .\install.ps1 -Auto                           # SQLite (zero config)
#   .\install.ps1 -Auto -MySQL                    # local MySQL
#   .\install.ps1 -Auto -Docker                   # MySQL via Docker
#   .\install.ps1 -Auto -DbHost remote.host       # remote MySQL
#
# Options:
#   -Auto            Non-interactive mode (no prompts)
#   -MySQL           Use MySQL/MariaDB backend (default is SQLite)
#   -Docker          Use Docker for MySQL (implies -MySQL)
#   -DbHost HOST     MySQL host (implies -MySQL; default: localhost)
#   -WithSemantic    Also install semantic search dependencies
#   -Upgrade         Upgrade existing Docker install (re-downloads files, rebuilds, restarts)
#   -Uninstall       Remove kanban-mcp (package, config, optionally DB and Docker data)
#

param(
    [switch]$Auto,
    [switch]$Docker,
    [switch]$MySQL,
    [string]$DbHost = "",
    [switch]$WithSemantic,
    [switch]$Upgrade,
    [switch]$Uninstall
)

# Wrap in a function so 'return' exits cleanly when piped via irm | iex
# (using 'exit' in a piped script kills the entire PowerShell host)
function Install-KanbanMcpServer {
    param(
        [switch]$Auto,
        [switch]$Docker,
        [switch]$MySQL,
        [string]$DbHost = "",
        [switch]$WithSemantic,
        [switch]$Upgrade,
        [switch]$Uninstall
    )

$ErrorActionPreference = "Stop"

$GithubRaw = "https://raw.githubusercontent.com/multidimensionalcats/kanban-mcp/main"
$ConfigDir = if ($env:APPDATA) { Join-Path $env:APPDATA "kanban-mcp" } else { Join-Path $HOME ".config/kanban-mcp" }

Write-Host "=== kanban-mcp Install ===" -ForegroundColor Cyan
Write-Host ""

# ─── Upgrade path (early exit) ────────────────────────────────────

if ($Upgrade) {
    $dockerDir = Join-Path $ConfigDir "docker"
    $composeFile = Join-Path $dockerDir "docker-compose.yml"

    if (-not (Test-Path $composeFile)) {
        Write-Host "Error: No Docker installation found at $dockerDir" -ForegroundColor Red
        Write-Host "For pipx upgrades:  pipx upgrade kanban-mcp"
        Write-Host "For fresh install:  .\install.ps1 -Docker"
        return
    }

    $env:PATH = [Environment]::GetEnvironmentVariable("PATH", "User") + ";" + [Environment]::GetEnvironmentVariable("PATH", "Machine")
    try {
        $null = Get-Command "docker" -ErrorAction Stop
        docker compose version 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) { throw }
    } catch {
        Write-Host "Error: Docker or docker compose not found." -ForegroundColor Red
        return
    }

    Write-Host "Upgrading Docker installation..."
    Write-Host ""

    # Upgrade the pipx package first so version detection is accurate
    Write-Host "Upgrading kanban-mcp package..."
    $ErrorActionPreference = "Continue"
    try { pipx upgrade kanban-mcp 2>$null } catch {}
    if ($LASTEXITCODE -ne 0) {
        try { pipx upgrade "kanban-mcp[mysql]" 2>$null } catch {}
    }
    $ErrorActionPreference = "Stop"
    Write-Host ""

    # Re-download Docker files pinned to the installed version
    Get-DockerFiles | Out-Null
    Write-Host ""

    # Load .env for compose
    $envFile = Join-Path $ConfigDir ".env"
    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
                [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
            }
        }
    }

    # Rebuild and restart
    Write-Host "Rebuilding web image..."
    docker compose -f $composeFile build --no-cache
    Write-Host ""

    Write-Host "Restarting services..."
    docker compose -f $composeFile up -d
    Write-Host ""

    Write-Host "=== Upgrade complete ===" -ForegroundColor Green
    Write-Host "The web container will run any pending database migrations on startup."
    Write-Host "Check logs: docker compose -f $composeFile logs -f web"
    return
}

# ─── Uninstall path (early exit) ─────────────────────────────────────

if ($Uninstall) {
    Write-Host "=== kanban-mcp Uninstall ===" -ForegroundColor Cyan
    Write-Host ""
    $removed = @()

    # 1. Remove pipx package
    $pipxList = ""
    try { $pipxList = pipx list 2>&1 } catch {}
    if ($pipxList -match "kanban-mcp") {
        Write-Host "Removing kanban-mcp package..."
        pipx uninstall kanban-mcp
        $removed += "kanban-mcp pipx package"
    } else {
        Write-Host "kanban-mcp pipx package not found (skipping)."
    }

    # Warn if kanban-mcp is still on PATH (pip/source install)
    $remaining = Get-Command "kanban-mcp" -ErrorAction SilentlyContinue
    if ($remaining) {
        Write-Host "Warning: kanban-mcp is still on PATH (likely a pip or source install)." -ForegroundColor Yellow
        Write-Host "  Location: $($remaining.Source)"
        Write-Host "  To remove: pip uninstall kanban-mcp"
    }
    Write-Host ""

    # 2. Docker cleanup
    $composeFile = Join-Path $ConfigDir "docker/docker-compose.yml"
    if (Test-Path $composeFile) {
        $dockerOk = $false
        $env:PATH = [Environment]::GetEnvironmentVariable("PATH", "User") + ";" + [Environment]::GetEnvironmentVariable("PATH", "Machine")
        try {
            $null = Get-Command "docker" -ErrorAction Stop
            docker compose version 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { $dockerOk = $true }
        } catch {}

        if ($dockerOk) {
            # Load .env so compose can resolve variables
            $envFile = Join-Path $ConfigDir ".env"
            if (Test-Path $envFile) {
                Get-Content $envFile | ForEach-Object {
                    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
                        [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
                    }
                }
            }

            Write-Host "Stopping Docker containers..."
            docker compose -f $composeFile down
            $removed += "Docker containers"

            if (-not $Auto) {
                Write-Host ""
                $removeVolume = Read-Host "Remove Docker data volume? This DELETES ALL kanban data. [y/N]"
                if (-not $removeVolume) { $removeVolume = "N" }
                if ($removeVolume -match "^[Yy]") {
                    docker compose -f $composeFile down -v
                    $removed += "Docker data volume"
                }
            }
        } else {
            Write-Host "Docker not available - skipping container cleanup."
            Write-Host "Docker files remain at: $(Join-Path $ConfigDir 'docker')"
        }
    }
    Write-Host ""

    # 3. MySQL database cleanup
    if (-not $Auto) {
        $dropDb = Read-Host "Drop MySQL database and user? [y/N]"
        if (-not $dropDb) { $dropDb = "N" }
        if ($dropDb -match "^[Yy]") {
            $dbName = if ($env:KANBAN_DB_NAME) { $env:KANBAN_DB_NAME } else { "kanban" }
            $dbUser = if ($env:KANBAN_DB_USER) { $env:KANBAN_DB_USER } else { "kanban" }
            $dbHostVal = if ($env:KANBAN_DB_HOST) { $env:KANBAN_DB_HOST } else { "localhost" }

            # Try loading from .env if not already set
            $envFile = Join-Path $ConfigDir ".env"
            if (Test-Path $envFile) {
                Get-Content $envFile | ForEach-Object {
                    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
                        [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
                    }
                }
                if ($env:KANBAN_DB_NAME) { $dbName = $env:KANBAN_DB_NAME }
                if ($env:KANBAN_DB_USER) { $dbUser = $env:KANBAN_DB_USER }
                if ($env:KANBAN_DB_HOST) { $dbHostVal = $env:KANBAN_DB_HOST }
            }

            Write-Host "Will drop database '$dbName' and user '$dbUser' on '$dbHostVal'."
            $mysqlAdmin = Read-Host "MySQL admin user [root]"
            if (-not $mysqlAdmin) { $mysqlAdmin = "root" }
            $mysqlAdminPw = Read-Host "MySQL admin password" -AsSecureString
            $mysqlAdminPwPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
                [Runtime.InteropServices.Marshal]::SecureStringToBSTR($mysqlAdminPw))

            if (Get-Command "mysql" -ErrorAction SilentlyContinue) {
                $sqlCmd = "DROP DATABASE IF EXISTS ``$dbName``; DROP USER IF EXISTS '$dbUser'@'%'; DROP USER IF EXISTS '$dbUser'@'localhost'; FLUSH PRIVILEGES;"
                $ErrorActionPreference = "Continue"
                mysql -h $dbHostVal -u $mysqlAdmin -p"$mysqlAdminPwPlain" -e $sqlCmd 2>$null
                if ($LASTEXITCODE -eq 0) {
                    $removed += "MySQL database '$dbName' and user '$dbUser'"
                } else {
                    Write-Host "Warning: Failed to drop database/user. You may need to do this manually." -ForegroundColor Yellow
                }
                $ErrorActionPreference = "Stop"
            } else {
                Write-Host "mysql client not found. Drop manually:" -ForegroundColor Yellow
                Write-Host "  DROP DATABASE IF EXISTS ``$dbName``;"
                Write-Host "  DROP USER IF EXISTS '$dbUser'@'localhost';"
            }
        }
    }
    Write-Host ""

    # 4. Remove config directory
    if (Test-Path $ConfigDir) {
        Write-Host "Removing config directory: $ConfigDir"
        Remove-Item -Recurse -Force $ConfigDir
        $removed += "Config directory ($ConfigDir)"
    }

    Write-Host ""
    Write-Host "=== Uninstall complete ===" -ForegroundColor Green
    if ($removed.Count -gt 0) {
        Write-Host ""
        Write-Host "Removed:"
        foreach ($item in $removed) {
            Write-Host "  - $item"
        }
    }
    Write-Host ""
    Write-Host "You may also want to remove kanban-mcp from your MCP client config."
    return
}

# ─── Helper functions ───────────────────────────────────────────────

function Test-Python {
    $script:Python = $null
    if (Get-Command "python3" -ErrorAction SilentlyContinue) {
        $script:Python = "python3"
    } elseif (Get-Command "python" -ErrorAction SilentlyContinue) {
        $script:Python = "python"
    } else {
        Write-Host "Error: Python 3.10+ is required but not found." -ForegroundColor Red
        Write-Host "Install Python from https://www.python.org/downloads/"
        return
    }

    $ver = & $script:Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    $parts = $ver -split '\.'
    $major = [int]$parts[0]
    $minor = [int]$parts[1]
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
        Write-Host "Error: Python 3.10+ is required (found $ver)." -ForegroundColor Red
        return
    }
    Write-Host "Found Python $ver"
}

function Test-Pipx {
    if (Get-Command "pipx" -ErrorAction SilentlyContinue) {
        Write-Host "Found pipx"
        return $true
    }
    return $false
}

function Install-Pipx {
    if (Get-Command "pipx" -ErrorAction SilentlyContinue) {
        Write-Host "Found pipx"
        return
    }
    # Check if pipx is available as a Python module before trying to install
    $pipxModule = & $script:Python -m pipx --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Found pipx (via $script:Python -m pipx)"
        try { & $script:Python -m pipx ensurepath 2>$null } catch {}
        return
    }
    Write-Host "Installing pipx..."
    $ErrorActionPreference = "Continue"
    & $script:Python -m pip install --user pipx 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        & $script:Python -m pip install pipx 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Error: Could not install pipx. Install it manually:" -ForegroundColor Red
            Write-Host "  https://pipx.pypa.io/stable/installation/"
            $ErrorActionPreference = "Stop"
            return
        }
    }
    $ErrorActionPreference = "Stop"
    try { & $script:Python -m pipx ensurepath 2>$null } catch {}
    # Refresh PATH
    $env:PATH = [Environment]::GetEnvironmentVariable("PATH", "User") + ";" + [Environment]::GetEnvironmentVariable("PATH", "Machine")
    if (-not (Get-Command "pipx" -ErrorAction SilentlyContinue)) {
        Write-Host "pipx installed but not in PATH. You may need to restart your shell."
    }
}

function Install-KanbanMcp {
    # Build extras string based on backend + semantic flags
    $extras = @()
    if ($script:Backend -eq "mysql") { $extras += "mysql" }
    if ($WithSemantic) { $extras += "semantic" }
    $extrasStr = $extras -join ","

    $pkg = "kanban-mcp"
    if ($extrasStr) { $pkg = "kanban-mcp[$extrasStr]" }

    # If run from a checkout with pyproject.toml, install from local
    # source instead of PyPI (ensures code and migrations match).
    $src = $pkg
    if (Test-Path "pyproject.toml") {
        $content = Get-Content "pyproject.toml" -Raw -ErrorAction SilentlyContinue
        if ($content -match 'name = "kanban-mcp"') {
            $src = "."
            if ($extrasStr) { $src = ".[$extrasStr]" }
            Write-Host "Installing $pkg from local checkout via pipx..."
        } else {
            Write-Host "Installing $pkg via pipx..."
        }
    } else {
        Write-Host "Installing $pkg via pipx..."
    }
    if (Get-Command "pipx" -ErrorAction SilentlyContinue) {
        pipx install $src
    } else {
        & $script:Python -m pipx install $src
    }
    Write-Host "kanban-mcp installed."
}

function Test-MysqlRunning {
    param([string]$Host_ = "localhost", [int]$Port = 3306)
    # Try TCP connection
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect($Host_, $Port)
        $tcp.Close()
        return $true
    } catch {
        return $false
    }
}

function Test-DockerAvailable {
    # Refresh PATH so newly-installed programs (e.g. Docker Desktop) are found
    $env:PATH = [Environment]::GetEnvironmentVariable("PATH", "User") + ";" + [Environment]::GetEnvironmentVariable("PATH", "Machine")
    try {
        $null = Get-Command "docker" -ErrorAction Stop
        docker compose version 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Get-InstalledVersion {
    # Get the installed kanban-mcp version for tag-pinned downloads.
    try {
        $ver = & python3 -c "from importlib.metadata import version; print(version('kanban-mcp'))" 2>$null
        if ($LASTEXITCODE -eq 0 -and $ver) { return $ver.Trim() }
    } catch {}
    try {
        $ver = & python -c "from importlib.metadata import version; print(version('kanban-mcp'))" 2>$null
        if ($LASTEXITCODE -eq 0 -and $ver) { return $ver.Trim() }
    } catch {}
    return ""
}

function Test-LocalCheckout {
    if (Test-Path "pyproject.toml") {
        $content = Get-Content "pyproject.toml" -Raw -ErrorAction SilentlyContinue
        return ($content -match 'name = "kanban-mcp"')
    }
    return $false
}

function Get-DockerFiles {
    $dockerDir = Join-Path $ConfigDir "docker"
    New-Item -ItemType Directory -Path $dockerDir -Force | Out-Null

    # Prefer local files from a checkout (guaranteed version match)
    if (Test-LocalCheckout) {
        Write-Host "Copying Docker files from local checkout..."
        Copy-Item "docker-compose.yml" -Destination (Join-Path $dockerDir "docker-compose.yml")
        Copy-Item "Dockerfile" -Destination (Join-Path $dockerDir "Dockerfile")
        Copy-Item "entrypoint.sh" -Destination (Join-Path $dockerDir "entrypoint.sh")
    } else {
        # Pin to installed version tag, fall back to main
        $ver = Get-InstalledVersion
        $rawUrl = $GithubRaw
        if ($ver) {
            $tagUrl = "https://raw.githubusercontent.com/multidimensionalcats/kanban-mcp/v${ver}"
            # Verify the tag exists before using it
            try {
                $null = Invoke-WebRequest -Uri "$tagUrl/Dockerfile" -Method Head -ErrorAction Stop
                $rawUrl = $tagUrl
                Write-Host "Downloading Docker files (pinned to v${ver})..."
            } catch {
                Write-Host "Downloading Docker files (from main, tag v${ver} not found)..."
            }
        } else {
            Write-Host "Downloading Docker files..."
        }
        Invoke-WebRequest -Uri "$rawUrl/docker-compose.yml" -OutFile (Join-Path $dockerDir "docker-compose.yml")
        Invoke-WebRequest -Uri "$rawUrl/Dockerfile" -OutFile (Join-Path $dockerDir "Dockerfile")
        Invoke-WebRequest -Uri "$rawUrl/entrypoint.sh" -OutFile (Join-Path $dockerDir "entrypoint.sh")
    }

    Write-Host "Docker files installed to $dockerDir"
    return $dockerDir
}

function Start-DockerMysql {
    param([string]$DockerDir)

    Write-Host "Starting MySQL via Docker Compose..."
    docker compose -f (Join-Path $DockerDir "docker-compose.yml") up -d

    Write-Host "Waiting for MySQL to become healthy..."
    $retries = 30
    while ($retries -gt 0) {
        $ps = docker compose -f (Join-Path $DockerDir "docker-compose.yml") ps 2>$null
        if ($ps -match "\(healthy\)") {
            Write-Host "MySQL is ready."
            return
        }
        $retries--
        Start-Sleep -Seconds 2
    }

    Write-Host "Warning: MySQL healthcheck timed out. It may still be starting." -ForegroundColor Yellow
    Write-Host "Check status with: docker compose -f $(Join-Path $DockerDir 'docker-compose.yml') ps"
}

function Invoke-DbSetup {
    param([string]$Host_, [string]$Name, [string]$User, [string]$Password, [string]$Port = "3306")

    Write-Host "--- Running kanban-setup ---"

    $env:KANBAN_DB_HOST = $Host_
    $env:KANBAN_DB_NAME = $Name
    $env:KANBAN_DB_USER = $User
    $env:KANBAN_DB_PASSWORD = $Password
    $env:KANBAN_DB_PORT = $Port
    if (-not $env:MYSQL_ROOT_USER) { $env:MYSQL_ROOT_USER = "root" }

    kanban-setup --auto
}

function Write-EnvFile {
    param([string]$Host_, [string]$User, [string]$Password, [string]$Name, [string]$Port = "3306")

    New-Item -ItemType Directory -Path $ConfigDir -Force | Out-Null
    $envFile = Join-Path $ConfigDir ".env"
    $writeIt = $true

    if (Test-Path $envFile) {
        if ($Auto) {
            # overwrite silently
        } else {
            $overwrite = Read-Host "$envFile already exists. Overwrite? [y/N]"
            if (-not $overwrite) { $overwrite = "N" }
            if ($overwrite -notmatch "^[Yy]") {
                Write-Host "Skipping .env generation."
                $writeIt = $false
            }
        }
    }

    if ($writeIt) {
        $content = @"
# kanban-mcp database configuration
KANBAN_DB_HOST=$Host_
KANBAN_DB_USER=$User
KANBAN_DB_PASSWORD=$Password
KANBAN_DB_NAME=$Name
"@
        if ($Port -ne "3306") {
            $content += "`nKANBAN_DB_PORT=$Port"
        }
        $content | Set-Content -Path $envFile -Encoding UTF8
        Write-Host "Created $envFile"
    }
}

function Write-NextSteps {
    param(
        [string]$Backend,
        [string]$Host_ = "",
        [string]$User = "",
        [string]$Password = "",
        [string]$Name = "",
        [switch]$IsDocker
    )

    Write-Host ""
    Write-Host "=== Setup complete ===" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:"
    Write-Host ""
    Write-Host "1. Add kanban-mcp to your MCP client config."
    Write-Host ""

    if ($Backend -eq "sqlite") {
        Write-Host "   Claude Desktop config:"
        Write-Host @"
   {
     "mcpServers": {
       "kanban": {
         "command": "kanban-mcp"
       }
     }
   }
"@
    } else {
        Write-Host "   Claude Desktop config:"
        Write-Host @"
   {
     "mcpServers": {
       "kanban": {
         "command": "kanban-mcp",
         "env": {
           "KANBAN_DB_HOST": "$Host_",
           "KANBAN_DB_USER": "$User",
           "KANBAN_DB_PASSWORD": "$Password",
           "KANBAN_DB_NAME": "$Name"
         }
       }
     }
   }
"@
    }

    Write-Host ""
    if ($Backend -eq "mysql" -and $IsDocker) {
        Write-Host "2. The web UI is running at http://localhost:5000"
    } else {
        Write-Host "2. Start the web UI (optional):"
        Write-Host "   kanban-web"
        Write-Host "   Open http://localhost:5000"
    }
    Write-Host ""
    Write-Host "3. Verify installation:"
    Write-Host "   kanban-cli --project C:\path\to\your\project summary"
    Write-Host ""

    # Print hook config snippet if hook commands are found
    $hookStart = Get-Command "kanban-hook-session-start" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
    $hookStop = Get-Command "kanban-hook-stop" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
    if ($hookStart -and $hookStop) {
        Write-Host "4. Set up hooks (recommended for Claude Code):"
        Write-Host ""
        Write-Host "   Hooks inject active kanban items at session start and"
        Write-Host "   prompt for progress updates when the session ends."
        Write-Host "   Without hooks, the agent only uses the board when asked."
        Write-Host ""
        Write-Host "   Merge into %USERPROFILE%\.claude\settings.json:"
        Write-Host ""
        Write-Host @"
   {
     "hooks": {
       "SessionStart": [
         { "hooks": [{ "type": "command", "command": "$hookStart" }] }
       ],
       "Stop": [
         { "hooks": [{ "type": "command", "command": "$hookStop" }] }
       ]
     }
   }
"@
        Write-Host ""
        Write-Host "   If you already have hooks configured, add the entries to"
        Write-Host "   the existing SessionStart and Stop arrays."
        Write-Host ""
    }
}

# ─── Step 1: Python & backend selection ─────────────────────────────

Test-Python

if (-not $script:Python) {
    # Test-Python failed — error already printed
    return
}

Write-Host ""

# ─── Choose backend (before install so we pick the right extras) ───

$script:Backend = ""   # "sqlite" or "mysql"
$MysqlMethod = ""      # "local", "remote", or "docker" (only when Backend=mysql)

if ($Docker -or $DbHost -or $MySQL) {
    $script:Backend = "mysql"
} elseif ($env:KANBAN_DB_USER -and $env:KANBAN_DB_PASSWORD -and $env:KANBAN_DB_NAME) {
    $script:Backend = "mysql"
} elseif ($Auto) {
    $script:Backend = "sqlite"
} else {
    Write-Host "Choose your database backend:"
    Write-Host "  1) SQLite (recommended, zero config)"
    Write-Host "  2) MySQL/MariaDB (local)"
    Write-Host "  3) MySQL/MariaDB (remote)"
    Write-Host "  4) MySQL via Docker"
    $choice = Read-Host "Choice [1]"
    if (-not $choice) { $choice = "1" }

    switch ($choice) {
        "1" { $script:Backend = "sqlite" }
        "2" { $script:Backend = "mysql"; $MysqlMethod = "local" }
        "3" { $script:Backend = "mysql"; $MysqlMethod = "remote" }
        "4" { $script:Backend = "mysql"; $MysqlMethod = "docker" }
        default {
            Write-Host "Invalid choice. Using SQLite."
            $script:Backend = "sqlite"
        }
    }
}

# For MySQL backend, determine connection method if not set above
if ($script:Backend -eq "mysql" -and -not $MysqlMethod) {
    if ($Docker) {
        $MysqlMethod = "docker"
    } elseif ($DbHost) {
        $MysqlMethod = "remote"
    } else {
        $MysqlMethod = "local"
    }
}

if ($script:Backend -eq "mysql") {
    switch ($MysqlMethod) {
        "local" {
            if (-not $DbHost) { $DbHost = if ($env:KANBAN_DB_HOST) { $env:KANBAN_DB_HOST } else { "localhost" } }
            if (Test-MysqlRunning -Host_ $DbHost) {
                Write-Host "MySQL is running on $DbHost."
            } else {
                Write-Host "MySQL is not running on $DbHost."
                if (Test-DockerAvailable) {
                    if ($Auto) {
                        Write-Host "Use -Docker flag to start MySQL via Docker."
                        Write-Host "Or start MySQL manually and re-run this script."
                        return
                    }
                    $startDocker = Read-Host "Start MySQL via Docker? [Y/n]"
                    if (-not $startDocker) { $startDocker = "Y" }
                    if ($startDocker -match "^[Yy]") {
                        $MysqlMethod = "docker"
                    } else {
                        Write-Host ""
                        Write-Host "Please start MySQL and re-run this script."
                        return
                    }
                } else {
                    Write-Host ""
                    Write-Host "Docker is not available either. Please install MySQL or Docker:"
                    Write-Host "  MySQL: https://dev.mysql.com/downloads/"
                    Write-Host "  Docker: https://docs.docker.com/get-docker/"
                    return
                }
            }
        }
        "remote" {
            if (-not $DbHost) {
                $DbHost = Read-Host "MySQL host"
            }
            if (-not $DbHost) {
                Write-Host "Error: No host provided." -ForegroundColor Red
                return
            }
            $DbPort = "3306"
            if (-not $Auto) {
                $portInput = Read-Host "MySQL port [$DbPort]"
                if ($portInput) { $DbPort = $portInput }
            }
            Write-Host "Will connect to MySQL at ${DbHost}:${DbPort}"
        }
        "docker" {
            if (-not (Test-DockerAvailable)) {
                Write-Host "Error: Docker is not installed or docker compose is not available." -ForegroundColor Red
                Write-Host "Install Docker: https://docs.docker.com/get-docker/"
                return
            }
        }
    }
}

Write-Host ""

# ─── Step 2: Install kanban-mcp ────────────────────────────────────

if (-not (Get-Command "kanban-mcp" -ErrorAction SilentlyContinue)) {
    Write-Host ""
    if ($Auto) {
        if (-not (Test-Pipx)) { Install-Pipx }
        Install-KanbanMcp
    } else {
        Write-Host "kanban-mcp is not installed."
        $installIt = Read-Host "Install kanban-mcp via pipx? [Y/n]"
        if (-not $installIt) { $installIt = "Y" }
        if ($installIt -match "^[Yy]") {
            if (-not (Test-Pipx)) { Install-Pipx }
            Install-KanbanMcp
        } else {
            Write-Host "Skipping kanban-mcp install. You can install manually with: pipx install kanban-mcp"
        }
    }
} else {
    Write-Host "Found kanban-mcp"
}

Write-Host ""

# ─── Step 3: Execute the chosen path ────────────────────────────────

if ($script:Backend -eq "sqlite") {
    # SQLite path: zero config, just run setup + migrations
    Write-Host "Setting up SQLite backend..."
    kanban-setup --auto --backend sqlite
    Write-NextSteps -Backend "sqlite"

} elseif ($MysqlMethod -eq "docker") {
    $dbName = if ($env:KANBAN_DB_NAME) { $env:KANBAN_DB_NAME } else { "kanban" }
    $dbUser = if ($env:KANBAN_DB_USER) { $env:KANBAN_DB_USER } else { "kanban" }
    $dbPassword = if ($env:KANBAN_DB_PASSWORD) { $env:KANBAN_DB_PASSWORD } else { "changeme" }
    $DbHost = "localhost"
    $DbPort = if ($env:KANBAN_DB_PORT) { $env:KANBAN_DB_PORT } else { "3306" }

    # Check for port conflict before starting Docker MySQL
    if (Test-MysqlRunning -Host_ $DbHost -Port ([int]$DbPort)) {
        Write-Host "Warning: Port $DbPort is already in use on $DbHost." -ForegroundColor Yellow
        if ($Auto) {
            Write-Host "Set KANBAN_DB_PORT to use a different port."
            return
        }
        $altPort = [int]$DbPort + 1
        $useAlt = Read-Host "Use alternative port $altPort instead? [Y/n]"
        if (-not $useAlt) { $useAlt = "Y" }
        if ($useAlt -match "^[Yy]") {
            $DbPort = "$altPort"
            Write-Host "Using port $DbPort."
        } else {
            $customPort = Read-Host "Enter port number"
            if (-not $customPort) {
                Write-Host "No port specified. Aborting."
                return
            }
            $DbPort = $customPort
            Write-Host "Using port $DbPort."
        }
    }

    $dockerDir = Get-DockerFiles
    Write-Host ""

    # Set env vars for docker-compose.yml
    $env:KANBAN_DB_NAME = $dbName
    $env:KANBAN_DB_USER = $dbUser
    $env:KANBAN_DB_PASSWORD = $dbPassword
    $env:KANBAN_DB_PORT = $DbPort

    Start-DockerMysql -DockerDir $dockerDir
    Write-Host ""

    Write-EnvFile -Host_ $DbHost -User $dbUser -Password $dbPassword -Name $dbName -Port $DbPort
    Write-NextSteps -Backend "mysql" -Host_ $DbHost -User $dbUser -Password $dbPassword -Name $dbName -IsDocker

    Write-Host "Docker compose files: $dockerDir"
    Write-Host "Manage with: docker compose -f $(Join-Path $dockerDir 'docker-compose.yml') [up|down|logs]"
    Write-Host ""

} else {
    # Local or remote MySQL: gather creds and run DB setup

    if ($Auto) {
        $dbName = if ($env:KANBAN_DB_NAME) { $env:KANBAN_DB_NAME } else { "kanban" }
        $dbUser = if ($env:KANBAN_DB_USER) { $env:KANBAN_DB_USER } else { "kanban" }
        if (-not $DbHost) { $DbHost = if ($env:KANBAN_DB_HOST) { $env:KANBAN_DB_HOST } else { "localhost" } }

        if ($env:KANBAN_DB_PASSWORD) {
            $dbPassword = $env:KANBAN_DB_PASSWORD
        } else {
            $dbPassword = & $script:Python -c "import secrets; print(secrets.token_urlsafe(16))"
            Write-Host "Generated password: $dbPassword"
        }
    } else {
        $dbName = Read-Host "Database name [kanban]"
        if (-not $dbName) { $dbName = "kanban" }

        $dbUser = Read-Host "Database user [kanban]"
        if (-not $dbUser) { $dbUser = "kanban" }

        $dbPwSecure = Read-Host "Database password (leave blank to auto-generate)" -AsSecureString
        $dbPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($dbPwSecure))
        if (-not $dbPassword) {
            $dbPassword = & $script:Python -c "import secrets; print(secrets.token_urlsafe(16))"
            Write-Host "Generated password: $dbPassword"
        }

        if ($MysqlMethod -eq "local" -and -not $DbHost) {
            $DbHost = "localhost"
        }

        $rootUserInput = Read-Host "MySQL root user for setup [root]"
        if ($rootUserInput) { $env:MYSQL_ROOT_USER = $rootUserInput }

        $rootPwSecure = Read-Host "MySQL root password (blank for socket auth)" -AsSecureString
        $rootPwPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($rootPwSecure))
        if ($rootPwPlain) { $env:MYSQL_ROOT_PASSWORD = $rootPwPlain }
    }

    Write-Host ""
    Write-Host "Configuration:"
    Write-Host "  Database: $dbName"
    Write-Host "  User:     $dbUser"
    Write-Host "  Host:     $DbHost"
    Write-Host ""

    if (-not $Auto) {
        $confirm = Read-Host "Proceed? [Y/n]"
        if (-not $confirm) { $confirm = "Y" }
        if ($confirm -notmatch "^[Yy]") {
            Write-Host "Aborted."
            return
        }
    }

    Invoke-DbSetup -Host_ $DbHost -Name $dbName -User $dbUser -Password $dbPassword -Port $(if ($DbPort) { $DbPort } else { "3306" })

    $portVal = if ($DbPort) { $DbPort } else { "3306" }
    Write-EnvFile -Host_ $DbHost -User $dbUser -Password $dbPassword -Name $dbName -Port $portVal
    Write-NextSteps -Backend "mysql" -Host_ $DbHost -User $dbUser -Password $dbPassword -Name $dbName
}

} # end Install-KanbanMcpServer

# Run the installer — pass script-level params into the function explicitly
$splat = @{}
if ($Auto) { $splat.Auto = $true }
if ($Docker) { $splat.Docker = $true }
if ($MySQL) { $splat.MySQL = $true }
if ($DbHost) { $splat.DbHost = $DbHost }
if ($WithSemantic) { $splat.WithSemantic = $true }
if ($Upgrade) { $splat.Upgrade = $true }
if ($Uninstall) { $splat.Uninstall = $true }
Install-KanbanMcpServer @splat
