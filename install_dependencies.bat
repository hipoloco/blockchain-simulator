@echo off

REM Moverse al directorio donde está ubicado el script
cd /d %~dp0

REM Verificar si pip está instalado
where pip >nul 2>nul
if %errorlevel% neq 0 (
    echo pip no está instalado. Por favor, instálalo antes de continuar.
    exit /b 1
)

REM Verificar si el archivo requirements.txt existe
if not exist requirements.txt (
    echo El archivo requirements.txt no se encuentra en el directorio.
    exit /b 1
)

echo Instalando dependencias desde requirements.txt...
pip install -r requirements.txt

if %errorlevel% equ 0 (
    echo Instalación completada exitosamente.
) else (
    echo Ocurrió un error durante la instalación de las dependencias.
    exit /b 1
)