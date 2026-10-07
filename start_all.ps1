$py = "D:\consensusdb\.venv313\Scripts\python.exe"
foreach ($i in "g1n1","g1n2","g1n3","g2n1","g2n2","g2n3") {
    Start-Process powershell -ArgumentList "-NoExit","-Command","cd D:\consensusdb; & '$py' run_node.py $i"
}
Start-Process powershell -ArgumentList "-NoExit","-Command","cd D:\consensusdb; & '$py' router.py"