# ConsensusDB: ek baar me sab. Isko D:\consensusdb me rakh ke chala:
#   powershell -ExecutionPolicy Bypass -File .\fix_and_test.ps1
$ErrorActionPreference = "SilentlyContinue"
Set-Location $PSScriptRoot
$py = Join-Path $PSScriptRoot ".venv313\Scripts\python.exe"
$log = New-Object System.Collections.ArrayList
function Say($m) { Write-Host $m; [void]$log.Add($m) }

# ---------- 1) port 8000 pe jitne purane routers hain sab maaro ----------
Say "== 1) purane routers band kar raha hoon =="
1..15 | ForEach-Object {
    Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
    Start-Sleep -Milliseconds 500
}
if (Get-NetTCPConnection -LocalPort 8000 -State Listen) {
    Say "PORT 8000 ABHI BHI BUSY. Saari PowerShell windows band kar (Raft nodes wali bhi), phir ye script dobara chala."
    exit
}
Say "port 8000 khali hai"

# ---------- 2) bench.py ke table naam letters-only (digit/underscore lexer ko shayad pasand nahi) ----------
$patch = @'
p = "bench/bench.py"
s = open(p, encoding="utf-8").read()
old = '    tables = [f"bench_{int(time.time())}_{k}" for k in range(a.tables)]'
new = '    import random, string\n    tag = "".join(random.choices(string.ascii_lowercase, k=5))\n    tables = [f"bench{tag}{chr(97 + k)}" for k in range(a.tables)]'
if old in s:
    open(p, "w", encoding="utf-8").write(s.replace(old, new))
    print("bench.py patched")
else:
    print("bench.py already patched / alag hai")
'@
$patch | & $py -

# ---------- 3) naya router alag window me ----------
Say "== 2) naya router start (alag window khulegi, usko band mat karna) =="
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$PSScriptRoot'; & '$py' router.py"
Start-Sleep -Seconds 3

function Q($path, $t, $sql) {
    $b = @{ table = $t; sql = $sql } | ConvertTo-Json -Compress
    try {
        Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000$path" -Body $b -ContentType "application/json" -TimeoutSec 10 | ConvertTo-Json -Compress -Depth 6
    } catch { "EXC: " + $_.Exception.Message }
}
function P($path) {
    try {
        Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000$path" -Body "{}" -ContentType "application/json" -TimeoutSec 30
    } catch { $null }
}

$st = P "/stats"
if ($null -eq $st -or $null -ne $st.error) {
    Say "ROUTER NAYA NAHI HAI ya chala nahi (/stats = $($st | ConvertTo-Json -Compress)). Naye router window ka error copy karke bhej."
    $log | Out-File diag_output.txt
    exit
}
Say "naya router chal raha hai (/stats ok)"

# ---------- 4) mkdb syntax test: kaunsa naam/syntax chalta hai ----------
Say "== 3) mkdb syntax test =="
$names = @("abc", "abc2", "a_b")
$works = @()
foreach ($n in $names) {
    $c = Q "/sql" $n "CREATE TABLE $n (id INT, name TEXT)"
    $i = Q "/sql" $n "INSERT INTO $n VALUES (1, 'x')"
    Start-Sleep -Milliseconds 700
    $s = Q "/query" $n "SELECT * FROM $n WHERE id = 1"
    Say "[$n] create=$c"
    Say "[$n] insert=$i"
    Say "[$n] select=$s"
    if ($s -notmatch '"error"' -and $s -notmatch "EXC") { $works += $n; Say "[$n] => CHALTA HAI" } else { Say "[$n] => FAIL" }
}

if ($works.Count -eq 0) {
    Say ""
    Say "KOI BHI NAAM NAHI CHALA. Matlab mkdb ko CREATE TABLE/INT/TEXT ka syntax hi nahi jam raha ya apply me error ignore ho raha hai."
    Say "Neeche wali lines bhej: tests\test_mkdb_sm.py me jo SQL hai"
    Get-Content tests\test_mkdb_sm.py | Select-String "CREATE|INSERT|SELECT" | ForEach-Object { Say $_.Line.Trim() }
    $log | Out-File diag_output.txt
    Say "(sab kuchh diag_output.txt me bhi save hai)"
    exit
}
Say "kam se kam ye naam chalte hain: $($works -join ', ')"

# ---------- 5) bench + optimizer ----------
Say "== 4) bench (chhota) =="
& $py -m bench.bench --tables 2 --rows 100 --threads 4 2>&1 | ForEach-Object { Say $_ }
Say "== 5) optimizer =="
$r = P "/optimize/run"
if ($r) {
    Say "source: $($r.source)   llm_error: $($r.llm_error)"
    foreach ($s in $r.suggestions) { Say "SUGGESTION [$($s.id)]: $($s.ddl)  speedup~$($s.cost.est_speedup_x)x" }
    foreach ($n in $r.notes) { Say "NOTE: $n" }
    foreach ($x in $r.rejected) { Say "REJECTED: $($x.reason)" }
    if (-not $r.suggestions) { Say "(koi suggestion nahi - ya to data kam hai ya selects fail hue)" }
}
$log | Out-File diag_output.txt
Say "(sab kuchh diag_output.txt me save hai)"
