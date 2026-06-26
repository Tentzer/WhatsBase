@echo off
cd /d %~dp0
:: Force recompile — clear cached bytecode so edits are always picked up.
if exist tests\__pycache__ rmdir /s /q tests\__pycache__
if exist app\__pycache__ rmdir /s /q app\__pycache__
python -m pytest tests -q 2>&1
