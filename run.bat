@echo off
echo Starting Video Translator API...
python -m uvicorn app.api.main_api:app --reload
pause