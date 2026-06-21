@echo off
setlocal

if "%RSNA_CTP_ROOT%"=="" (
  set "RSNA_CTP_ROOT=%~dp0installed\CTP\CTP"
)

java -jar "%RSNA_CTP_ROOT%\Runner.jar" %*
exit /b %ERRORLEVEL%
