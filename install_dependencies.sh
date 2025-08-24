#!/bin/bash

# Moverse al directorio donde está ubicado el script
cd "$(dirname "$0")"

# Verificar si pip está instalado
if ! command -v pip &> /dev/null
then
    echo "pip no está instalado. Por favor, instálalo antes de continuar."
    exit 1
fi

# Verificar si el archivo requirements.txt existe
if [ ! -f "requirements.txt" ]; then
    echo "El archivo requirements.txt no se encuentra en el directorio."
    exit 1
fi

echo "Instalando dependencias desde requirements.txt..."
pip install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "Instalación completada exitosamente."
else
    echo "Ocurrió un error durante la instalación de las dependencias."
    exit 1
fi