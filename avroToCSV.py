"""
avroToCSV.py
=======
Paso 2 del pipeline: convierte los archivos AVRO crudos de una pulsera y un día
en CSV (uno por sensor).

Entrada : ./cyberduck/<FECHA>/<DISPOSITIVO>/raw/*.avro        (los deja dataDownload.sh)
Salida  : ./cyberduck/<FECHA>/<DISPOSITIVO>/processed/<sensor>.csv

Uso:
    1. Editar FECHA y DISPOSITIVO.
    2. Dejar activadas (sin '#') solo las exportaciones que se necesiten:
         - pulsera del evaluado  -> señales biométricas (acelerómetro, EDA, temperatura,
                                    BVP, pasos, picos sistólicos)
         - pulsera del evaluador -> solo tags
    3. python avroToCSV.py

Los AVRO de un día se procesan en orden; el primero sobrescribe los CSV y el resto
añade filas, de modo que cada CSV contiene todo el día.
"""
import os
import avro_utils

# --- Configuración (editar en cada ejecución) -------------------------------
FECHA = "2026-05-29"
DISPOSITIVO = "HV"

RAW_DIR = f"./cyberduck/{FECHA}/{DISPOSITIVO}/raw/"
OUTPUT_DIR = f"./cyberduck/{FECHA}/{DISPOSITIVO}/processed/"


def exportar_sensores(avro_file_path, mode):
    """
    Exporta los sensores deseados de un AVRO. Comentar/descomentar según la pulsera.
    """
    # --- Pulsera del evaluado (señales biométricas) ---
    avro_utils.export_accelerometer_to_csv(avro_file_path, OUTPUT_DIR, mode=mode)
    avro_utils.export_eda_to_csv(avro_file_path, OUTPUT_DIR, mode=mode)
    avro_utils.export_temperature_to_csv(avro_file_path, OUTPUT_DIR, mode=mode)
    avro_utils.export_bvp_to_csv(avro_file_path, OUTPUT_DIR, mode=mode)
    avro_utils.export_steps_to_csv(avro_file_path, OUTPUT_DIR, mode=mode)
    avro_utils.export_systolic_peaks_to_csv(avro_file_path, OUTPUT_DIR, mode=mode)

    # --- Pulsera del evaluador (tags) ---
    #avro_utils.export_tags_to_csv(avro_file_path, OUTPUT_DIR, mode=mode)


def main():
    avro_files = sorted(f for f in os.listdir(RAW_DIR) if f.endswith(".avro"))

    if not avro_files:
        print(f"❌ No se encontraron archivos AVRO en {RAW_DIR}")
        return

    print(f"📂 Encontrados {len(avro_files)} archivos AVRO. Procesando en lote...")

    first = None  # primer registro de la sesión (para el resumen final)

    for i, filename in enumerate(avro_files):
        avro_file_path = os.path.join(RAW_DIR, filename)

        # 'w' en el primero (crea/sobrescribe los CSV), 'a' en los siguientes (añade)
        mode = "w" if i == 0 else "a"

        try:
            exportar_sensores(avro_file_path, mode)

            if i == 0:
                print(f"\n--- INICIO DE LA SESIÓN ({filename}) ---")
                reader, _ = avro_utils.open_avro_file(avro_file_path)
                first, _ = avro_utils.get_first_and_last_records(reader)
                info = avro_utils.get_participant_info(first)
                print(f"Participante: {info['participant_id']} | Dispositivo: {info['device_sn']}")
                _, dt = avro_utils.get_study_start_time(first)
                print(f"Inicio sesión: {dt}")
                reader.close()

            if i == len(avro_files) - 1:
                print(f"\n--- FIN DE LA SESIÓN ({filename}) ---")
                reader, _ = avro_utils.open_avro_file(avro_file_path)
                _, last = avro_utils.get_first_and_last_records(reader)
                _, dt = avro_utils.get_study_end_time(last)
                print(f"Final sesión: {dt}")
                avro_utils.print_record_summary(first, last)
                reader.close()

        except Exception as e:
            print(f"❌ Error procesando {filename}: {e}")

    print(f"\n✅ Proceso completado. CSV unificados en {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
