"""
avro_utils.py
=============
Utilidades para leer los archivos AVRO (datos crudos) de la pulsera Empatica EmbracePlus
y exportarlos a CSV, un archivo por sensor.

Es usado por ``main.py``. Cada función ``export_*_to_csv`` escribe un CSV con la
señal de un sensor; si se llama con ``mode="a"`` añade filas a un CSV existente
(así se unen varios AVRO consecutivos de un mismo día en un único CSV).

Formato de los CSV generados
----------------------------
* accelerometer.csv   -> unix_timestamp_micros, datetime_utc, x_g, y_g, z_g
* eda.csv             -> unix_timestamp_micros, datetime_utc, eda_microsiemens
* temperature.csv     -> unix_timestamp_micros, datetime_utc, temperature_celsius
* bvp.csv             -> unix_timestamp_micros, datetime_utc, bvp_value
* steps.csv           -> unix_timestamp_micros, datetime_utc, step_count
* tags.csv            -> tags_timestamp (µs), datetime_utc
* systolic_peaks.csv  -> unix_timestamp_nanos, datetime_utc

NOTA: la columna ``datetime_utc`` se genera con ``datetime.fromtimestamp`` y por tanto
está en la **hora local del equipo** donde se ejecuta el script, no en UTC estricto.
Todo el pipeline (separate_participant.py y graficarTiempoFreq.py) es coherente con
esto: las horas de inicio/fin que se indican y las del eje X de las gráficas son
horas locales. Los timestamps numéricos (``unix_timestamp_*``) sí son Unix epoch.
"""
from avro.datafile import DataFileReader
from avro.io import DatumReader
from datetime import datetime
import json
import os
import csv


# ---------------------------------------------------------------------------
# Lectura de metadatos del AVRO (resumen de la sesión)
# ---------------------------------------------------------------------------

def open_avro_file(file_path):
    """
    Abre un archivo AVRO.

    Args:
        file_path (str): Ruta del archivo AVRO.

    Returns:
        tuple: (reader, schema) - ``DataFileReader`` abierto y esquema AVRO como dict.
               El llamador debe cerrar el reader con ``reader.close()``.
    """
    reader = DataFileReader(open(file_path, "rb"), DatumReader())
    schema = json.loads(reader.meta.get("avro.schema").decode("utf-8"))
    return reader, schema


def get_first_and_last_records(reader):
    """
    Recorre todo el archivo y devuelve su primer y último registro.

    Args:
        reader: ``DataFileReader`` (se consume al iterarlo).

    Returns:
        tuple: (first_record, last_record)
    """
    first_record = None
    last_record = None

    for record in reader:
        if first_record is None:
            first_record = record
        last_record = record

    return first_record, last_record


def get_study_start_time(first_record):
    """
    Instante de inicio de la sesión, tomando el acelerómetro como sensor de referencia.

    Args:
        first_record (dict): Primer registro AVRO.

    Returns:
        tuple: (timestamp_micros, datetime) o (None, None) si no hay datos válidos.
    """
    if not first_record:
        return None, None

    raw_data = first_record.get("rawData", {})

    if raw_data.get("accelerometer"):
        acc = raw_data["accelerometer"]
        ts_micros = acc.get("timestampStart")
        if ts_micros and ts_micros > 0:
            dt = datetime.fromtimestamp(ts_micros / 1_000_000)
            return ts_micros, dt

    return None, None


def get_study_end_time(last_record):
    """
    Instante de fin de la sesión: inicio del último bloque del acelerómetro
    más la duración de ese bloque (nº de muestras / frecuencia de muestreo).

    Args:
        last_record (dict): Último registro AVRO.

    Returns:
        tuple: (timestamp_micros, datetime) o (None, None) si no hay datos válidos.
    """
    if not last_record:
        return None, None

    raw_data = last_record.get("rawData", {})

    if raw_data.get("accelerometer"):
        acc = raw_data["accelerometer"]
        ts_start_micros = acc.get("timestampStart")
        frequency = acc.get("samplingFrequency", 0)
        num_samples = len(acc.get("x", []))

        if ts_start_micros and ts_start_micros > 0 and frequency > 0 and num_samples > 0:
            last_block_duration = num_samples / frequency
            end_seconds = (ts_start_micros / 1_000_000) + last_block_duration
            ts_end_micros = int(end_seconds * 1_000_000)
            dt = datetime.fromtimestamp(end_seconds)
            return ts_end_micros, dt

    return None, None


def get_study_duration(first_record, last_record):
    """
    Duración total de la sesión en segundos (None si no se puede calcular).
    """
    ts_start, _ = get_study_start_time(first_record)
    ts_end, _ = get_study_end_time(last_record)

    if ts_start is None or ts_end is None:
        return None

    return (ts_end - ts_start) / 1_000_000


def get_available_sensors(record):
    """
    Lista los sensores con datos en un registro, con su frecuencia de muestreo
    y número de muestras.

    Args:
        record (dict): Registro AVRO.

    Returns:
        dict: {nombre_sensor: {available, sampling_frequency,
               sampling_interval_seconds, timestamp_start, num_samples}}
    """
    raw_data = record.get("rawData", {})
    sensors = {}

    for sensor_name, sensor_data in raw_data.items():
        if not sensor_data:
            continue

        sampling_freq = sensor_data.get("samplingFrequency")
        sampling_interval = None
        if sampling_freq and sampling_freq > 0:
            sampling_interval = 1.0 / sampling_freq

        sensor_info = {
            "available": True,
            "sampling_frequency": sampling_freq,
            "sampling_interval_seconds": sampling_interval,
            "timestamp_start": sensor_data.get("timestampStart")
        }

        # Número de muestras: depende de la estructura de cada sensor
        if "values" in sensor_data:
            sensor_info["num_samples"] = len(sensor_data["values"])
        elif "x" in sensor_data:
            sensor_info["num_samples"] = len(sensor_data["x"])
        elif "tagsTimeMicros" in sensor_data:
            sensor_info["num_samples"] = len(sensor_data["tagsTimeMicros"])
        elif "peaksTimeNanos" in sensor_data:
            sensor_info["num_samples"] = len(sensor_data["peaksTimeNanos"])

        sensors[sensor_name] = sensor_info

    return sensors


def get_participant_info(record):
    """
    Información de identificación (participante, estudio, dispositivo) de un registro.

    Returns:
        dict: participant_id, study_id, site_id, organization_id, device_sn, device_model
    """
    enrollment = record.get("enrollment", {})

    return {
        "participant_id": enrollment.get("participantID"),
        "study_id": enrollment.get("studyID"),
        "site_id": enrollment.get("siteID"),
        "organization_id": enrollment.get("organizationID"),
        "device_sn": record.get("deviceSn", "N/A"),
        "device_model": record.get("deviceModel", "N/A")
    }


def print_record_summary(first_record, last_record):
    """
    Imprime por consola un resumen de la sesión: participante, dispositivo,
    inicio/fin/duración y sensores disponibles.
    """
    if not first_record or not last_record:
        print("❌ No hay registros disponibles")
        return

    print("\n" + "=" * 80)
    print("📊 RESUMEN DEL ARCHIVO AVRO")
    print("=" * 80)

    participant = get_participant_info(first_record)
    print(f"\n👤 ID: {participant['participant_id']}")
    print(f"\n📱 DISPOSITIVO: {participant['device_sn']}")

    _, dt_start = get_study_start_time(first_record)
    _, dt_end = get_study_end_time(last_record)
    duration = get_study_duration(first_record, last_record)

    print("\n⏱️  TIEMPOS:")
    if dt_start:
        print(f"   Inicio: {dt_start.strftime('%Y-%m-%d %H:%M:%S')}")
    if dt_end:
        print(f"   Final: {dt_end.strftime('%Y-%m-%d %H:%M:%S')}")
    if duration:
        hours = int(duration // 3600)
        minutes = int((duration % 3600) // 60)
        seconds = int(duration % 60)
        print(f"   Duración: {hours}h {minutes}m {seconds}s")

    sensors = get_available_sensors(first_record)
    print(f"\n🔬 SENSORES DISPONIBLES ({len(sensors)}):")
    for sensor_name, sensor_info in sorted(sensors.items()):
        num_samples = sensor_info.get("num_samples", "?")
        freq = sensor_info.get("sampling_frequency", "?")
        interval = sensor_info.get("sampling_interval_seconds")

        if interval:
            print(f"   ✓ {sensor_name}: {num_samples} muestras @ {freq} Hz (cada {interval * 1000:.2f} ms)")
        else:
            print(f"   ✓ {sensor_name}: {num_samples} muestras @ {freq} Hz")

    print("\n" + "=" * 80 + "\n")


# ---------------------------------------------------------------------------
# Extracción de filas por tipo de sensor (generadores)
# ---------------------------------------------------------------------------

def _get_start_and_freq(sensor_data):
    """Devuelve (timestampStart en µs, frecuencia en Hz) o (None, None) si no son válidos."""
    if not sensor_data:
        return None, None
    ts = sensor_data.get("timestampStart")
    freq = sensor_data.get("samplingFrequency")
    if not ts or freq is None or freq <= 0:
        return None, None
    return ts, freq


def _extract_accelerometer_rows(sensor_data):
    """
    Genera las filas [timestamp_µs, datetime, x_g, y_g, z_g] de un bloque del acelerómetro.

    El AVRO guarda el timestamp solo de la primera muestra del bloque; el de cada muestra
    se reconstruye como inicio + i * (1 / frecuencia). Los valores digitales (ADC) se
    convierten a g con el factor (physicalMax - physicalMin) / (digitalMax - digitalMin).
    """
    start_ts, freq = _get_start_and_freq(sensor_data)
    if not start_ts:
        return

    sampling_interval_micros = 1e6 / freq

    imu_params = sensor_data["imuParams"]
    try:
        delta_physical = imu_params["physicalMax"] - imu_params["physicalMin"]
        delta_digital = imu_params["digitalMax"] - imu_params["digitalMin"]
        factor = delta_physical / delta_digital
    except ZeroDivisionError:  # límites digitales iguales: no se aplica conversión
        factor = 1.0

    x_vals = sensor_data.get("x", [])
    y_vals = sensor_data.get("y", [])
    z_vals = sensor_data.get("z", [])

    # Se asume que los tres ejes tienen la misma longitud
    for i in range(len(x_vals)):
        ts_micros = int(start_ts + (i * sampling_interval_micros))
        dt = datetime.fromtimestamp(ts_micros / 1e6).strftime('%Y-%m-%d %H:%M:%S.%f')

        yield [
            ts_micros,
            dt,
            x_vals[i] * factor,
            y_vals[i] * factor,
            z_vals[i] * factor
        ]


def _extract_simple_values_rows(sensor_data):
    """
    Genera las filas [timestamp_µs, datetime, valor] para sensores con un único
    array ``values`` (EDA, temperatura, BVP, pasos). Timestamps reconstruidos igual
    que en el acelerómetro.
    """
    start_ts, freq = _get_start_and_freq(sensor_data)
    if not start_ts:
        return

    sampling_interval_micros = 1e6 / freq
    values = sensor_data.get("values", [])

    for i, val in enumerate(values):
        ts_micros = int(start_ts + (i * sampling_interval_micros))
        dt = datetime.fromtimestamp(ts_micros / 1e6).strftime('%Y-%m-%d %H:%M:%S.%f')
        yield [ts_micros, dt, val]


# ---------------------------------------------------------------------------
# Exportación a CSV
# ---------------------------------------------------------------------------

def _export_sensor_generic(avro_file_path, output_dir, output_filename, sensor_name,
                           csv_headers, row_extractor_func, mode="w"):
    """
    Exporta los datos de un sensor de un archivo AVRO a CSV.

    Args:
        avro_file_path (str): AVRO de entrada.
        output_dir (str): Directorio de salida (se crea si no existe).
        output_filename (str): Nombre del CSV.
        sensor_name (str): Clave del sensor dentro de ``rawData`` (p. ej. "eda", "systolicPeaks").
        csv_headers (list): Cabecera del CSV.
        row_extractor_func (callable): Recibe los datos del sensor y genera las filas.
        mode (str): "w" sobrescribe (y escribe cabecera); "a" añade al final
                    (cabecera solo si el archivo no existe o está vacío).
    """
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, output_filename)

    write_header = True
    if mode == "a" and os.path.exists(output_file) and os.path.getsize(output_file) > 0:
        write_header = False

    print(f"🔄 Exportando {sensor_name.upper()} de {os.path.basename(avro_file_path)} a {output_filename}...")

    try:
        reader = DataFileReader(open(avro_file_path, "rb"), DatumReader())

        with open(output_file, mode=mode, newline="") as f:
            writer = csv.writer(f)

            if write_header:
                writer.writerow(csv_headers)

            for record in reader:
                sensor_data = record.get("rawData", {}).get(sensor_name)
                if not sensor_data:
                    continue
                for row in row_extractor_func(sensor_data):
                    writer.writerow(row)

        reader.close()

    except Exception as e:
        print(f"❌ Error al exportar {sensor_name}: {e}")


def export_accelerometer_to_csv(avro_file_path, output_dir, output_filename="accelerometer.csv", mode="w"):
    """Exporta el acelerómetro (ejes x, y, z en g)."""
    _export_sensor_generic(
        avro_file_path, output_dir, output_filename, "accelerometer",
        ["unix_timestamp_micros", "datetime_utc", "x_g", "y_g", "z_g"],
        _extract_accelerometer_rows, mode
    )


def export_eda_to_csv(avro_file_path, output_dir, output_filename="eda.csv", mode="w"):
    """Exporta la actividad electrodérmica (EDA, en microsiemens)."""
    _export_sensor_generic(
        avro_file_path, output_dir, output_filename, "eda",
        ["unix_timestamp_micros", "datetime_utc", "eda_microsiemens"],
        _extract_simple_values_rows, mode
    )


def export_temperature_to_csv(avro_file_path, output_dir, output_filename="temperature.csv", mode="w"):
    """Exporta la temperatura cutánea (ºC)."""
    _export_sensor_generic(
        avro_file_path, output_dir, output_filename, "temperature",
        ["unix_timestamp_micros", "datetime_utc", "temperature_celsius"],
        _extract_simple_values_rows, mode
    )


def export_bvp_to_csv(avro_file_path, output_dir, output_filename="bvp.csv", mode="w"):
    """Exporta el pulso de volumen sanguíneo (BVP)."""
    _export_sensor_generic(
        avro_file_path, output_dir, output_filename, "bvp",
        ["unix_timestamp_micros", "datetime_utc", "bvp_value"],
        _extract_simple_values_rows, mode
    )


def export_steps_to_csv(avro_file_path, output_dir, output_filename="steps.csv", mode="w"):
    """Exporta el contador de pasos."""
    _export_sensor_generic(
        avro_file_path, output_dir, output_filename, "steps",
        ["unix_timestamp_micros", "datetime_utc", "step_count"],
        _extract_simple_values_rows, mode
    )


def export_tags_to_csv(avro_file_path, output_dir, output_filename="tags.csv", mode="w"):
    """
    Exporta los tags (pulsaciones del botón de la pulsera). ``tags_timestamp`` está en µs.
    Se usa con la pulsera del evaluador.
    """
    _export_sensor_generic(
        avro_file_path, output_dir, output_filename, "tags",
        ["tags_timestamp", "datetime_utc"],
        lambda sensor_data: (
            [ts, datetime.fromtimestamp(ts / 1e6).strftime('%Y-%m-%d %H:%M:%S.%f')]
            for ts in sensor_data.get("tagsTimeMicros", [])
        ),
        mode
    )


def export_systolic_peaks_to_csv(avro_file_path, output_dir, output_filename="systolic_peaks.csv", mode="w"):
    """
    Exporta los picos sistólicos detectados (timestamps en nanosegundos).
    De ellos se deriva después la frecuencia de pulso (ver separate_participant.py).
    """
    _export_sensor_generic(
        avro_file_path, output_dir, output_filename, "systolicPeaks",
        ["unix_timestamp_nanos", "datetime_utc"],
        lambda sensor_data: (
            [ts, datetime.fromtimestamp(ts / 1e9).strftime('%Y-%m-%d %H:%M:%S.%f')]
            for ts in sensor_data.get("peaksTimeNanos", [])
        ),
        mode
    )
