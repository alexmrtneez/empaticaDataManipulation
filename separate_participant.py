"""
separate_participant.py
=======================
Paso 3 del pipeline: recorta los CSV de un día completo (salida de main.py) a la
ventana horaria de UN participante y los guarda en su carpeta.

Entrada :
    ./cyberduck/<fecha>/<dev>/processed/<sensor>.csv        pulsera del evaluado
    ./cyberduck/<fecha>/<dev_tags>/processed/tags.csv       pulsera del evaluador
Salida  : ./data/<fase>/<center>/<center>_<id>-<fecha>/
    <id_completo>_<sensor>.csv      accelerometer, bvp, eda, steps, temperature, systolic_peaks
    <id_completo>_pulse_rate.csv    frecuencia de pulso (BPM) derivada de los picos sistólicos
    <id_completo>_tags_orig.csv     tags tal como los grabó la pulsera del evaluador
    <id_completo>_tags_mod.csv      copia de tags_orig para corregir A MANO (ver tags_def.py)

Argumentos:
    center       Código del centro/estudio (p. ej. ECO). Prefijo del id del participante.
    fecha        Fecha de la sesión (yyyy-MM-dd o yyyyMMdd).
    dev          Prefijo de la pulsera del evaluado (carpeta en cyberduck/<fecha>/).
    dev_tags     Prefijo de la pulsera del evaluador (carpeta en cyberduck/<fecha>/).
    id           Número del participante (p. ej. 001) -> id completo "ECO_001".
    fase         "pre" o "post": protocolo realizado antes/después de instalar la
                 señalización accesible en el parque (separa los datos en directorios).
    hora_inicio  Inicio de la sesión del participante (HH, HHMM, HH:MM, HHMMSS o HH:MM:SS).
    hora_fin     Fin de la sesión (mismo formato). Si solo se da hora o minuto, el fin
                 incluye ese periodo completo (p. ej. "10:50" llega hasta 10:50:59.999999).

Las horas se interpretan en la misma referencia que la columna ``datetime_utc`` de los
CSV (hora local del equipo que ejecutó main.py; ver nota en avro_utils.py).
"""
import os
import sys
import pandas as pd
import numpy as np

# Sensores de la pulsera del evaluado que se recortan para cada participante
features = [
    "accelerometer",
    "bvp",
    "eda",
    "steps",
    "temperature",
    "systolic_peaks"
]


def calcular_pulso_desde_nanos(participant_dir, id_completo):
    """
    Calcula la frecuencia de pulso instantánea (BPM) a partir de los picos sistólicos
    ya recortados del participante y la guarda en ``<id_completo>_pulse_rate.csv``.

    Para cada pico: BPM = 60 / (intervalo en segundos respecto al pico anterior).
    El primer pico, y los intervalos <= 0 (timestamps duplicados), quedan sin valor.
    """
    input_file = os.path.join(participant_dir, f"{id_completo}_systolic_peaks.csv")
    output_file = os.path.join(participant_dir, f"{id_completo}_pulse_rate.csv")

    df = pd.read_csv(input_file)

    # Intervalo entre picos consecutivos (ns -> s)
    df['diff_nanos'] = df['unix_timestamp_nanos'].diff()
    df['ibi_seconds'] = df['diff_nanos'] / 1e9

    # Se evita dividir por cero si el sensor repite un timestamp
    df['pulso_bpm'] = np.where(
        df['ibi_seconds'] > 0,
        60.0 / df['ibi_seconds'],
        pd.NA)

    df_final = df[['id', 'unix_timestamp_nanos', 'datetime_utc', 'pulso_bpm']].copy()
    df_final.to_csv(output_file, index=False)
    print(f"Procesamiento completado. Archivo guardado como: '{output_file}'")


def parse_datetime_from_date_and_time(fecha, hora, is_end=False):
    """
    Convierte fecha + hora (strings) en un Timestamp.

    Si ``is_end`` es True y la hora solo tiene precisión de hora o minuto, se devuelve el
    último microsegundo de ese periodo, para que el fin de la ventana sea inclusivo.

    Raises:
        ValueError: si la hora no coincide con ningún formato admitido.
    """
    if hora is None:
        return None

    date_fmt = "%Y-%m-%d" if "-" in fecha else "%Y%m%d"
    time_formatos = [
        ("%H", "hour"),
        ("%H%M", "minute"),
        ("%H:%M", "minute"),
        ("%H%M%S", "second"),
        ("%H:%M:%S", "second")
    ]

    for time_fmt, precision in time_formatos:
        try:
            ts = pd.to_datetime(f"{fecha} {hora}", format=f"{date_fmt} {time_fmt}", utc=True)
            if is_end:
                if precision == "hour":
                    ts = ts + pd.Timedelta(hours=1) - pd.Timedelta(microseconds=1)
                elif precision == "minute":
                    ts = ts + pd.Timedelta(minutes=1) - pd.Timedelta(microseconds=1)
            return ts
        except (ValueError, TypeError):
            continue

    raise ValueError(f"Formato de hora no válido: {hora}")


def extract_feature(feature, id_completo, start_time, end_time, processed_dir, participant_dir):
    """
    Recorta ``<processed_dir>/<feature>.csv`` a [start_time, end_time], añade la columna
    ``id`` al principio y lo guarda en la carpeta del participante.

    Casos especiales:
      * feature == "tags": se guardan dos copias, ``_tags_orig.csv`` (original) y
        ``_tags_mod.csv`` (con columna extra ``insert='empatica'``), esta última para editarla a mano.
      * feature == "systolic_peaks": además se genera ``_pulse_rate.csv``.
    """
    input_file = os.path.join(processed_dir, f"{feature}.csv")
    output_file = os.path.join(participant_dir, f"{id_completo}_{feature}.csv")

    if feature == "tags":
        output_file = os.path.join(participant_dir, f"{id_completo}_tags_orig.csv")
        output_file_mod = os.path.join(participant_dir, f"{id_completo}_tags_mod.csv")

    if not os.path.exists(input_file):
        print(f"❌ Archivo no encontrado: {input_file}")
        return

    try:
        df = pd.read_csv(input_file)

        # Columna temporal usada para filtrar (todos los CSV de main.py tienen datetime_utc;
        # las otras ramas son un respaldo por si faltase)
        if 'datetime_utc' in df.columns:
            ts_col = 'datetime_utc'
            df[ts_col] = pd.to_datetime(df[ts_col], utc=True)
        elif 'unix_timestamp_nanos' in df.columns:
            ts_col = 'unix_timestamp_nanos'
            if pd.api.types.is_numeric_dtype(df[ts_col]):
                df[ts_col] = pd.to_datetime(df[ts_col], unit='ns', utc=True)
            else:
                df[ts_col] = pd.to_datetime(df[ts_col], utc=True)
        elif 'unix_timestamp_micros' in df.columns:
            ts_col = 'unix_timestamp_micros'
            if pd.api.types.is_numeric_dtype(df[ts_col]):
                df[ts_col] = pd.to_datetime(df[ts_col], unit='us', utc=True)
            else:
                df[ts_col] = pd.to_datetime(df[ts_col], utc=True)
        else:
            ts_col = None

        if ts_col is not None:
            if start_time is not None and end_time is not None:
                df = df[df[ts_col].between(start_time, end_time)]
            else:
                if start_time is not None:
                    df = df[df[ts_col] >= start_time]
                if end_time is not None:
                    df = df[df[ts_col] <= end_time]

        df.insert(0, 'id', id_completo)
        df.to_csv(output_file, index=False)

        if feature == "tags":
            df_copy = df.copy()
            df_copy['insert'] = 'empatica'
            df_copy.to_csv(output_file_mod, index=False)

        if feature == "systolic_peaks":
            calcular_pulso_desde_nanos(participant_dir, id_completo)

        print(f"✅ {feature} extraído correctamente a {output_file}")
    except Exception as e:
        print(f"❌ Error al procesar {feature}: {e}")


def usage():
    print(
        "Uso: python3 separate_participant.py <center> <fecha> <dev> <dev_tags> <id> <fase> <hora_inicio> <hora_fin>"
    )
    print("Ejemplo: python3 separate_participant.py ECO 2026-05-15 HV FY 001 pre 10:32 11:10")
    print("  dev       = pulsera del evaluado | dev_tags = pulsera del evaluador")
    print("  fase      = pre | post")
    print("Formato de fecha: yyyy-MM-dd o yyyyMMdd")
    print("Formato de hora: HH, HHMM, HH:MM, HHMMSS o HH:MM:SS")


def main():
    if len(sys.argv) != 9 or sys.argv[1] in ("-h", "--help"):
        usage()
        sys.exit(1)

    center = sys.argv[1]
    fecha = sys.argv[2]
    dev = sys.argv[3]
    dev_tags = sys.argv[4]
    id_completo = center + "_" + sys.argv[5]
    fase = sys.argv[6]
    hora_inicio = sys.argv[7]
    hora_fin = sys.argv[8]

    processed_dir = f"./cyberduck/{fecha}/{dev}/processed/"
    processed_dir_tags = f"./cyberduck/{fecha}/{dev_tags}/processed/"
    participant_dir = f"./data/{fase}/{center}/{id_completo}-{fecha}"

    os.makedirs(participant_dir, exist_ok=True)

    inicio = parse_datetime_from_date_and_time(fecha, hora_inicio, is_end=False)
    fin = parse_datetime_from_date_and_time(fecha, hora_fin, is_end=True)

    for feature in features:
        extract_feature(feature, id_completo, inicio, fin, processed_dir, participant_dir)

    # Los tags vienen de la pulsera del evaluador
    extract_feature("tags", id_completo, inicio, fin, processed_dir_tags, participant_dir)


if __name__ == "__main__":
    main()
