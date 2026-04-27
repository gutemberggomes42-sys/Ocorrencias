@echo off
setlocal
cd /d "%~dp0"

set "BUNDLED_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

where python >nul 2>nul
if %errorlevel%==0 (
  python server.py
  goto :eof
)

where py >nul 2>nul
if %errorlevel%==0 (
  py server.py
  goto :eof
)

if exist "%BUNDLED_PYTHON%" (
  "%BUNDLED_PYTHON%" server.py
  goto :eof
)

echo Python nao encontrado.
echo Instale o Python ou execute usando o runtime do Codex.
pause
