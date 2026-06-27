# PowerShell Launcher for Standalone Backtester Dashboard
# Activates conda environment and launches Streamlit server

Set-Location $PSScriptRoot
$env:PYTHONPATH = "$PSScriptRoot\.."

Write-Host "Activating conda environment QuFLX-v2..." -ForegroundColor Green
conda activate QuFLX-v2

Write-Host "Starting Streamlit Dashboard..." -ForegroundColor Green
streamlit run ui/dashboard.py
