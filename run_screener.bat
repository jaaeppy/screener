@echo off
cd /d C:\Users\dinky\screener
C:\Users\dinky\AppData\Local\Programs\Python\Python311\python.exe screener.py
git add screener_result.json index.html sector.html
git commit -m "daily update"
git push origin main
pause
