@echo off
setlocal

if "%MIDI_VALIDATOR_PYTHON%"=="" (
  set "MIDI_VALIDATOR_PYTHON=D:\CodexExternal\venvs\midi-validation-311\Scripts\python.exe"
)
if "%MIDI_VALIDATOR_ROOT%"=="" (
  set "MIDI_VALIDATOR_ROOT=%~dp0midi-validation-script"
)
if "%MIDI_VALIDATOR_NLTK_DATA%"=="" (
  set "MIDI_VALIDATOR_NLTK_DATA=D:\CodexExternal\nltk_data"
)

set "NLTK_DATA=%MIDI_VALIDATOR_NLTK_DATA%"
"%MIDI_VALIDATOR_PYTHON%" "%MIDI_VALIDATOR_ROOT%\run_validation.py" %*
exit /b %ERRORLEVEL%
