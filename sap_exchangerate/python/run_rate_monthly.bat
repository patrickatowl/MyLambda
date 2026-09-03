@echo off

:: 1. 呼叫 Anaconda 的啟動腳本並啟用 webapi 環境
:: (請確認下方 Anaconda3 的路徑是否與你電腦實際安裝的位置相符)
call "C:\ProgramData\anaconda3\Scripts\activate.bat" webapi

:: 2. 切換到程式資料夾
cd /d "C:\Users\czber\repo\MyLambda\sap_exchangerate\python"

:: 3. 執行 Python 程式
python send_rate.py

:: (非必要) 執行完畢後關閉 conda 環境
call conda deactivate