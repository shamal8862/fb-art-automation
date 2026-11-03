@echo off
echo Installing Facebook Art Scheduler to Windows Startup...
set "TARGET_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%TARGET_DIR%\ArtSchedulerStartup.vbs"

copy /y "c:\xampp\htdocs\fb-art-automation\startup\run_silent.vbs" "%SHORTCUT_PATH%" >nul
if exist "%SHORTCUT_PATH%" (
    echo [SUCCESS] Art Scheduler installed to Windows Startup!
    echo It will now run silently in the background whenever your laptop powers on.
) else (
    echo [ERROR] Failed to copy to Startup folder.
)
pause
