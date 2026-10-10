$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$py = if ($env:CONSENSUSDB_PYTHON) { $env:CONSENSUSDB_PYTHON } else { "python" }
foreach ($i in "g1n1","g1n2","g1n3","g2n1","g2n2","g2n3") {
    Start-Process -FilePath $py -ArgumentList "run_node.py",$i -WorkingDirectory $root
}
Start-Process -FilePath $py -ArgumentList "router.py" -WorkingDirectory $root
