#
# kanban-mcp database setup script (Windows PowerShell)
# Sets up MySQL database, user, and runs migrations.
# Requires: mysql client in PATH, MySQL 8.0+ server running
#
# Interactive (default):
#   .\install.ps1
#
# Non-interactive (for AI agents / automation):
#   .\install.ps1 -Auto
#   Uses env vars or defaults: KANBAN_DB_NAME, KANBAN_DB_USER,
#   KANBAN_DB_PASSWORD (auto-generated if unset), KANBAN_DB_HOST,
#   MYSQL_ROOT_USER, MYSQL_ROOT_PASSWORD
#
# Options:
#   -Auto            Non-interactive mode (no prompts)
#   -WithSemantic    Also install semantic search dependencies
#

param(
    [switch]$Auto,
    [switch]$WithSemantic
)

$ErrorActionPreference = "Stop"

Write-Host "=== kanban-mcp Database Setup ===" -ForegroundColor Cyan
Write-Host ""

# Check mysql client is available
if (-not (Get-Command "mysql" -ErrorAction SilentlyContinue)) {
    Write-Host "Error: mysql client not found." -ForegroundColor Red
    Write-Host "Install MySQL and ensure mysql.exe is in your PATH."
    Write-Host "Download: https://dev.mysql.com/downloads/mysql/"
    exit 1
}

# Find migration files
$MigrationsDir = $null
if (Test-Path ".\kanban_mcp\migrations") {
    $MigrationsDir = ".\kanban_mcp\migrations"
} else {
    try {
        $PackageDir = python -c "import kanban_mcp; import os; print(os.path.dirname(kanban_mcp.__file__))" 2>$null
        if ($PackageDir -and (Test-Path "$PackageDir\migrations")) {
            $MigrationsDir = "$PackageDir\migrations"
        }
    } catch {}
}

if (-not $MigrationsDir) {
    Write-Host "Error: Could not find migration files." -ForegroundColor Red
    Write-Host "Run this script from the kanban-mcp repo root, or ensure kanban-mcp is pip-installed."
    exit 1
}

Write-Host "Found migrations in: $MigrationsDir"
Write-Host ""

# --- Gather configuration ---

if ($Auto) {
    $DbName = if ($env:KANBAN_DB_NAME) { $env:KANBAN_DB_NAME } else { "kanban" }
    $DbUser = if ($env:KANBAN_DB_USER) { $env:KANBAN_DB_USER } else { "kanban" }
    $DbHost = if ($env:KANBAN_DB_HOST) { $env:KANBAN_DB_HOST } else { "localhost" }
    $MysqlRootUser = if ($env:MYSQL_ROOT_USER) { $env:MYSQL_ROOT_USER } else { "root" }
    $MysqlRootPassword = $env:MYSQL_ROOT_PASSWORD

    if ($env:KANBAN_DB_PASSWORD) {
        $DbPassword = $env:KANBAN_DB_PASSWORD
    } else {
        $DbPassword = python -c "import secrets; print(secrets.token_urlsafe(16))"
        Write-Host "Generated password: $DbPassword"
    }
} else {
    $DbName = Read-Host "Database name [kanban]"
    if (-not $DbName) { $DbName = "kanban" }

    $DbUser = Read-Host "Database user [kanban]"
    if (-not $DbUser) { $DbUser = "kanban" }

    $DbPassword = Read-Host "Database password (leave blank to auto-generate)"
    if (-not $DbPassword) {
        $DbPassword = python -c "import secrets; print(secrets.token_urlsafe(16))"
        Write-Host "Generated password: $DbPassword"
    }

    $DbHost = Read-Host "Database host [localhost]"
    if (-not $DbHost) { $DbHost = "localhost" }

    $MysqlRootUser = Read-Host "MySQL root user for setup [root]"
    if (-not $MysqlRootUser) { $MysqlRootUser = "root" }

    $MysqlRootPassword = $null
}

Write-Host ""
Write-Host "Configuration:"
Write-Host "  Database: $DbName"
Write-Host "  User:     $DbUser"
Write-Host "  Host:     $DbHost"
Write-Host ""

if (-not $Auto) {
    $Confirm = Read-Host "Proceed? [Y/n]"
    if (-not $Confirm) { $Confirm = "Y" }
    if ($Confirm -notmatch "^[Yy]") {
        Write-Host "Aborted."
        exit 0
    }
}

# --- Create database and user ---

Write-Host "--- Creating database and user ---"

$SetupSql = @"
CREATE DATABASE IF NOT EXISTS ``$DbName`` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$DbUser'@'%' IDENTIFIED BY '$DbPassword';
GRANT ALL PRIVILEGES ON ``$DbName``.* TO '$DbUser'@'%';
FLUSH PRIVILEGES;
"@

if ($MysqlRootPassword) {
    $SetupSql | mysql -u $MysqlRootUser -p"$MysqlRootPassword" -h $DbHost
} elseif (-not $Auto) {
    Write-Host "(You may be prompted for the MySQL root password)"
    $SetupSql | mysql -u $MysqlRootUser -p -h $DbHost
} else {
    # Auto mode without root password — try without password (e.g. socket auth)
    $SetupSql | mysql -u $MysqlRootUser -h $DbHost
}

Write-Host "Database and user created."

# --- Run migrations ---

Write-Host ""
Write-Host "--- Running migrations ---"

Get-ChildItem "$MigrationsDir\0*.sql" | Sort-Object Name | ForEach-Object {
    Write-Host "  Applying $($_.Name)..."
    Get-Content $_.FullName -Raw | mysql -u $DbUser -p"$DbPassword" -h $DbHost $DbName
}

Write-Host "Migrations complete."

# --- Install semantic dependencies ---

if ($WithSemantic) {
    Write-Host ""
    Write-Host "--- Installing semantic search dependencies ---"
    pip install "kanban-mcp[semantic]"
    Write-Host "Semantic search dependencies installed."
}

# --- Generate .env file ---

$EnvFile = ".env"
$WriteEnv = $true

if (Test-Path $EnvFile) {
    if ($Auto) {
        # Auto mode: overwrite silently
    } else {
        $Overwrite = Read-Host ".env file already exists. Overwrite? [y/N]"
        if (-not $Overwrite) { $Overwrite = "N" }
        if ($Overwrite -notmatch "^[Yy]") {
            Write-Host "Skipping .env generation."
            $WriteEnv = $false
        }
    }
}

if ($WriteEnv) {
    @"
# kanban-mcp database configuration
KANBAN_DB_HOST=$DbHost
KANBAN_DB_USER=$DbUser
KANBAN_DB_PASSWORD=$DbPassword
KANBAN_DB_NAME=$DbName
"@ | Set-Content -Path $EnvFile -Encoding UTF8

    Write-Host "Created $EnvFile"
}

Write-Host ""
Write-Host "=== Setup complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host ""
Write-Host "1. Add kanban-mcp to your MCP client config."
Write-Host ""
Write-Host "   Claude Desktop (~/.config/Claude/claude_desktop_config.json):"
Write-Host @"
   {
     "mcpServers": {
       "kanban": {
         "command": "kanban-mcp",
         "env": {
           "KANBAN_DB_HOST": "$DbHost",
           "KANBAN_DB_USER": "$DbUser",
           "KANBAN_DB_PASSWORD": "$DbPassword",
           "KANBAN_DB_NAME": "$DbName"
         }
       }
     }
   }
"@
Write-Host ""
Write-Host "2. Start the web UI (optional):"
Write-Host "   kanban-web"
Write-Host "   Open http://localhost:5000"
Write-Host ""
Write-Host "3. Verify installation:"
Write-Host "   kanban-cli --project C:\path\to\your\project summary"
Write-Host ""
