param(
    [string]$SuperUser = 'postgres',
    [string]$DbHost = 'localhost',
    [int]$Port = 5432,
    [string]$Database = 'autocare',
    [string]$AppUser = 'autocare_user'
)

if (-not (Get-Command psql -ErrorAction SilentlyContinue)) {
    Write-Error "psql not found in PATH. Install PostgreSQL client or add it to PATH."
    exit 1
}

# Prompt for the superuser password securely
Write-Host "Enter password for Postgres superuser '$SuperUser':"
$secure = Read-Host -AsSecureString
$BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
$plain = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)

# Set password in env for psql to pick up
$env:PGPASSWORD = $plain
try {
    $sql = "GRANT USAGE ON SCHEMA public TO $AppUser; GRANT CREATE ON SCHEMA public TO $AppUser;"
    Write-Host "Running grants on database '$Database'..."
    $uri = "postgresql://${SuperUser}@${DbHost}:${Port}/${Database}"
    psql $uri -c $sql
    Write-Host "Grants applied. You can now restart the app or run init_db()."
} finally {
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
    # zero-out plain variable
    $plain = $null
}
