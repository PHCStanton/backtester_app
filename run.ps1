# PowerShell Launcher for Standalone Backtester Dashboard
# Activates conda environment and launches Streamlit server

Set-Location $PSScriptRoot
$env:PYTHONPATH = "$PSScriptRoot\.."

Write-Host "Starting Streamlit Dashboard in Conda Environment QuFLX-v2..." -ForegroundColor Green
conda run --no-capture-output -n QuFLX-v2 streamlit run ui/dashboard.py
