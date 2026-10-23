@echo off
setlocal
cd /d "e:\GOOGLE AI STUDIO\SWING TRADING\MID CAP SWING"

echo ======================================================== >> scanner_cron.log
echo Daily Scan Started: %date% %time% >> scanner_cron.log
echo ======================================================== >> scanner_cron.log

set FORCE_ALERT=1

"C:\Python314\python.exe" main.py >> scanner_cron.log 2>&1
"C:\Python314\python.exe" archive_writer.py >> scanner_cron.log 2>&1
"C:\Python314\python.exe" fetch_deals.py >> scanner_cron.log 2>&1
"C:\Python314\python.exe" -c "import main; main.git_commit_scan_results()" >> scanner_cron.log 2>&1

echo Daily Scan Completed: %date% %time% >> scanner_cron.log
endlocal
