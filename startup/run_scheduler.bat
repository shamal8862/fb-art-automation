@echo off
cd /d "c:\xampp\htdocs\fb-art-automation"
echo [%date% %time%] Running Facebook Art Scheduler startup check... >> data\scheduler_startup.log
python scheduler.py >> data\scheduler_startup.log 2>&1
