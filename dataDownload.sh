#!/bin/bash
#
# dataDownload.sh
# ===============
# Paso 1 del pipeline: descarga de S3 (Empatica) los datos crudos (AVRO) y los
# biomarcadores digitales de UNA pulsera en UN día, usando Cyberduck CLI (`duck`).
#
# Uso:
#   ./dataDownload.sh <FECHA> <ID_DISPOSITIVO>
#   ./dataDownload.sh 2026-05-15 HV
#
# <ID_DISPOSITIVO> es el prefijo de la pulsera (p. ej. HV). El script busca en S3 la
# carpeta del día cuyo nombre completo empieza y acaba por ese prefijo
# (p. ej. HV-3YK9J1H1HV). Un mismo día se ejecuta una vez por pulsera
# (evaluado y evaluador).
#
# Variables de entorno necesarias (NO se guardan en el repositorio):
#   EMPATICA_S3_USER   Access key ID con permiso de lectura sobre el bucket.
#   EMPATICA_S3_BASE   URL base de los datos de participantes de TU estudio, sin la fecha:
#                      s3://s3.amazonaws.com/<bucket>/v2/<org>/<estudio>/<sitio>/participant_data
# `duck` pedirá la clave secreta si no la tiene guardada en el llavero.
#
# Resultado:
#   ./cyberduck/<FECHA>/<ID_DISPOSITIVO>/raw/                 AVRO crudos  (los usa main.py)
#   ./cyberduck/<FECHA>/<ID_DISPOSITIVO>/digital_biomarkers/  agregados por minuto
#                                                             (no se usan en el resto del pipeline)

if [ "$#" -ne 2 ]; then
    echo "❌ Error: Faltan argumentos."
    echo "Uso: $0 <FECHA> <ID_DISPOSITIVO>"
    echo "Ejemplo: $0 2026-02-04 HV"
    exit 1
fi

: "${EMPATICA_S3_USER:?Define EMPATICA_S3_USER (access key ID)}"
: "${EMPATICA_S3_BASE:?Define EMPATICA_S3_BASE (s3://.../participant_data)}"

DATE=$1
DEVICE=$2

TARGET_DIR_RAW="./cyberduck/${DATE}/${DEVICE}/raw"
TARGET_DIR_BIO="./cyberduck/${DATE}/${DEVICE}/digital_biomarkers"
S3_BASE_URL="${EMPATICA_S3_BASE}/${DATE}"

echo "🔍 Buscando dispositivo que empiece por '$DEVICE' en S3 para la fecha $DATE..."

# Lista las carpetas del día, se queda con la última palabra de cada línea (el nombre)
# y filtra la que empieza y termina por el prefijo del dispositivo (ej. HV-3YK9J1H1HV).
FULL_DEVICE_ID=$(duck --username "$EMPATICA_S3_USER" --list "$S3_BASE_URL/" \
    | awk '{print $NF}' | tr -d '/' | grep "^${DEVICE}.*${DEVICE}$" | head -n 1)

if [ -z "$FULL_DEVICE_ID" ]; then
    echo "❌ No se encontró ningún dispositivo que empiece por '$DEVICE' en la ruta:"
    echo "   $S3_BASE_URL/"
    exit 1
fi

echo "✅ Dispositivo encontrado: $FULL_DEVICE_ID"

DOWNLOAD_URL_RAW="$S3_BASE_URL/$FULL_DEVICE_ID/raw_data/v6/1-1-$DEVICE*"
DOWNLOAD_URL_BIO="$S3_BASE_URL/$FULL_DEVICE_ID/digital_biomarkers/aggregated_per_minute/1-1-$DEVICE*"

echo "📂 Creando directorio local (datos crudos): $TARGET_DIR_RAW"
mkdir -p "$TARGET_DIR_RAW"

echo "⬇️  Iniciando descarga de: $DOWNLOAD_URL_RAW"
duck --username "$EMPATICA_S3_USER" --download "$DOWNLOAD_URL_RAW" "$TARGET_DIR_RAW" || {
    echo "❌ Ocurrió un error durante la descarga de datos crudos."; exit 1; }

echo "📂 Creando directorio local (biomarcadores): $TARGET_DIR_BIO"
mkdir -p "$TARGET_DIR_BIO"

echo "⬇️  Iniciando descarga de: $DOWNLOAD_URL_BIO"
duck --username "$EMPATICA_S3_USER" --download "$DOWNLOAD_URL_BIO" "$TARGET_DIR_BIO" || {
    echo "❌ Ocurrió un error durante la descarga de biomarcadores."; exit 1; }

echo "✅ Descarga completada con éxito."
echo "📄 Archivos en $TARGET_DIR_RAW:"
ls -lh "$TARGET_DIR_RAW"
echo "📄 Archivos en $TARGET_DIR_BIO:"
ls -lh "$TARGET_DIR_BIO"
