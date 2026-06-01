@echo off
REM Step 2 of the public-deploy: bake the ngrok URL into the frontend and
REM produce a dist\ folder you can drag onto https://app.netlify.com/drop.

setlocal
set "ROOT=%~dp0"
pushd "%ROOT%"

if "%~1"=="" (
    set /p NGROK_URL=Paste the ngrok URL (https://...ngrok-free.app):
) else (
    set "NGROK_URL=%~1"
)

if "%NGROK_URL%"=="" (
    echo No URL given, aborting.
    pause
    exit /b 1
)

REM Strip any trailing slash so VITE_API_URL ends cleanly
if "%NGROK_URL:~-1%"=="/" set "NGROK_URL=%NGROK_URL:~0,-1%"

echo Writing .env.production with VITE_API_URL=%NGROK_URL%
> .env.production echo VITE_API_URL=%NGROK_URL%

echo Building frontend...
call npm run build
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Done. The static site is in:
echo     %ROOT%dist
echo.
echo  Next:
echo   1. Open https://app.netlify.com/drop in your browser.
echo   2. Drag the dist folder onto the page.
echo   3. Wait a few seconds, copy the URL Netlify gives you.
echo   4. Send that URL to the teacher.
echo ============================================================
echo.

start "" "https://app.netlify.com/drop"
start "" "%ROOT%dist"

pause
popd
endlocal
