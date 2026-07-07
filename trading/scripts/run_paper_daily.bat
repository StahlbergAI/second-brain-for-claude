@echo off
rem Daily paper-trading run - registered in Windows Task Scheduler as "TradingPaperDaily".
rem Logs each run to trading\data\paper_runs.log so you can audit what happened.
cd /d "C:\Users\stahl\Desktop\second-brain-for-claude\trading"
echo. >> data\paper_runs.log
echo ===== %date% %time% ===== >> data\paper_runs.log
python scripts\run_paper.py >> data\paper_runs.log 2>&1
