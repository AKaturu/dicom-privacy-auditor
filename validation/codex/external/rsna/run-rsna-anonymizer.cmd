@echo off
setlocal

if "%RSNA_ANONYMIZER_EXE%"=="" (
  set "RSNA_ANONYMIZER_EXE=D:\CodexExternal\venvs\rsna-anonymizer-312\Scripts\rsna-anonymizer.exe"
)

"%RSNA_ANONYMIZER_EXE%" %*
exit /b %ERRORLEVEL%
