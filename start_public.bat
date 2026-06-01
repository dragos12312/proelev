@echo off
REM ProElev one-click public-deploy helper.
REM Opens two side-by-side windows: the backend and ngrok.
REM After ngrok prints its public URL, paste that URL into .env.production
REM and run `npm run build`, then drop dist\ on https://app.netlify.com/drop.

setlocal

REM Use the folder this .bat file lives in as the project root so we can be
REM double-clicked from anywhere
set "ROOT=%~dp0"
set "BACKEND=%ROOT%src\backend"

REM Sanity check, the backend folder exists
if not exist "%BACKEND%\main.py" (
    echo Couldn't find %BACKEND%\main.py
    echo Put start_public.bat in the project root, next to README.md.
    pause
    exit /b 1
)

REM Make sure the SQLite schema is up to date so the server starts cleanly
echo Applying any pending database migrations...
pushd "%BACKEND%"
python -m alembic upgrade head
if errorlevel 1 (
    echo.
    echo Migration failed. Run inside %BACKEND%:
    echo     python -m alembic stamp 19b052b1c739
    echo     python -m alembic upgrade head
    echo and try this script again.
    popd
    pause
    exit /b 1
)
popd

REM Window 1, plain HTTP uvicorn. ngrok wraps it in HTTPS so we skip the
REM --ssl-keyfile flags here.
start "ProElev Backend" cmd /k "cd /d %BACKEND% && python -m uvicorn main:app --host 0.0.0.0 --port 8000"

REM Give uvicorn ~3s to bind the port before ngrok tries to forward
timeout /t 3 /nobreak >nul

REM Window 2, ngrok. Free tier prints a random https://...-ngrok-free.app URL.
start "ProElev ngrok tunnel" cmd /k "ngrok http 8000"

REM Open the ngrok local web UI in a browser so the user can copy the URL
timeout /t 4 /nobreak >nul
start "" "http://localhost:4040"

echo.
echo ============================================================
echo  Backend + ngrok are starting in their own windows.
echo  In ~5 seconds your browser will open the ngrok web UI at
echo  http://localhost:4040 where you can see the public URL.
echo.
echo  Next steps:
echo   1. Copy the https://...ngrok-free.app URL from that page.
echo   2. Edit C:\Users\Dragos\proelev\.env.production so it reads:
echo         VITE_API_URL=https://that-url.ngrok-free.app
echo   3. cd C:\Users\Dragos\proelev
echo      npm run build
echo   4. Drag the dist\ folder to https://app.netlify.com/drop
echo   5. Send the Netlify URL to the teacher.
echo.
echo  Keep these two windows open while the teacher is testing.
echo ============================================================
echo.
pause
endlocal
