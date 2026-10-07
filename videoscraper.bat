@echo off
cd /d "%~dp0"
echo Starting Telegram media bot...
echo.
python bot.py
echo.
echo The bot stopped or could not start. Review the message above.
pause
