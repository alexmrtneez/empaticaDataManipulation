"""
tags_def.py
===========
Paso 4 del pipeline: genera el archivo de tags DEFINITIVO de un participante a partir de
``<id_completo>_tags_mod.csv`` (tags de la pulsera del evaluador, revisados a mano).

Entrada : data/<fase>/<center>/<id_completo>-<date>/<id_completo>_tags_mod.csv
Salida  : data/<fase>/<center>/<id_completo>-<date>/<id_completo>_tags.csv
          columnas: id, tags_timestamp, tag, extra

Cómo funciona
-------------
El evaluador pulsa el botón de la pulsera en cada hito del protocolo (56 tags, ver
Plantilla.pdf), siempre en el mismo orden. La pulsera solo registra el instante, no el
nombre, así que el nombre se asigna por POSICIÓN: la fila n recibe el n-ésimo nombre
del diccionario ``tags`` (más abajo).

Revisión manual previa (sobre tags_mod.csv):
  * Si falta algún tag que sí se anotó en la plantilla en papel, se duplica la fila
    anterior y se ajusta el timestamp, para que la secuencia vuelva a tener 56 filas.
  * Si se quiere anotar un suceso durante la sesión, se rellena la columna ``anotacion``
    en esa fila (si la columna no existe, se crea vacía). Esas filas se etiquetan como
    ``extra`` y NO consumen un nombre del diccionario.

En el CSV final, ``extra`` contiene el texto de la anotación para los tags "extra" y
0 (valor de relleno) para el resto.

Nota: los nombres usados aquí son los que consume graficarTiempoFreq.py; en
Plantilla.pdf algunos aparecen escritos de forma ligeramente distinta (p. ej.
ts_stressvulnerability_* = ts_sv_*, ts_emotions_* = ts_et_*, ts_baseline_* = ts_bl_*).

Uso:
    python tags_def.py <center> <date> <id_num> <fase>
    python tags_def.py ECO 2026-05-15 001 pre
"""

import os
import sys
import pandas as pd

# Nombres de los 56 tags, en el orden en que se pulsan durante el protocolo.
# (_inst_ = lectura de instrucciones; sin _inst_ = realización de la actividad/cuestionario)
tags = {
    # Basal: escala analógica visual 1, asistencia previa, cuestionarios
    "ts_eav1_start": 0,
    "ts_eav1_end": 0,
    "ts_att_start": 0,
    "ts_att_end": 0,
    "ts_inst_sv_start": 0,
    "ts_inst_sv_end": 0,
    "ts_sv_start": 0,            # Cuestionario de vulnerabilidad al estrés
    "ts_sv_end": 0,
    "ts_inst_sp_start": 0,
    "ts_inst_sp_end": 0,
    "ts_sp_start": 0,            # Cuestionario de estrés autopercibido
    "ts_sp_end": 0,
    # Actividad 1: Baño (+ retorno)
    "ts_inst_task1_start": 0,
    "ts_inst_task1_end": 0,
    "ts_task1_start": 0,
    "ts_task1_end": 0,
    "ts_inst_return1_start": 0,
    "ts_inst_return1_end": 0,
    "ts_return1_start": 0,
    "ts_return1_end": 0,
    # Actividad 2: Biodomo (+ retorno)
    "ts_inst_task2_start": 0,
    "ts_inst_task2_end": 0,
    "ts_task2_start": 0,
    "ts_task2_end": 0,
    "ts_inst_return2_start": 0,
    "ts_inst_return2_end": 0,
    "ts_return2_start": 0,
    "ts_return2_end": 0,
    # Actividad 3: Mariposario (+ retorno)
    "ts_inst_task3_start": 0,
    "ts_inst_task3_end": 0,
    "ts_task3_start": 0,
    "ts_task3_end": 0,
    "ts_inst_return3_start": 0,
    "ts_inst_return3_end": 0,
    "ts_return3_start": 0,
    "ts_return3_end": 0,
    # Actividad 4: Salida (+ retorno)
    "ts_inst_task4_start": 0,
    "ts_inst_task4_end": 0,
    "ts_task4_start": 0,
    "ts_task4_end": 0,
    "ts_inst_return4_start": 0,
    "ts_inst_return4_end": 0,
    "ts_return4_start": 0,
    "ts_return4_end": 0,
    # Posterior: escala analógica visual 2 y entrevista de sensaciones percibidas
    "ts_eav2_start": 0,
    "ts_eav2_end": 0,
    "ts_inst_et_start": 0,
    "ts_inst_et_end": 0,
    "ts_et_start": 0,
    "ts_et_end": 0,
    # Recuperación: tarea de línea base y escala analógica visual 3
    "ts_inst_bl_start": 0,
    "ts_inst_bl_end": 0,
    "ts_bl_start": 0,
    "ts_bl_end": 0,
    "ts_eav3_start": 0,
    "ts_eav3_end": 0
}


def extrae_tags(tags_mod, id_completo, ruta):
    """
    Asigna a cada fila de ``tags_mod`` el nombre de tag que le corresponde por posición
    y guarda ``<id_completo>_tags.csv`` en ``ruta``.

    Las filas con valor en la columna ``anotacion`` se etiquetan como "extra" (guardando
    el texto en la columna ``extra``) y no avanzan en el diccionario de tags.

    Args:
        tags_mod (DataFrame): contenido de ``<id_completo>_tags_mod.csv``.
        id_completo (str): p. ej. "ECO_001".
        ruta (str): carpeta del participante.
    """
    if 'anotacion' not in tags_mod.columns:
        tags_mod['anotacion'] = pd.NA

    rows_list = []
    tag_keys = list(tags.keys())
    tag_idx = 0  # posición en el diccionario; solo avanza con tags "normales"

    for i, row in tags_mod.iterrows():
        anotacion = row.get('anotacion')

        if pd.notna(anotacion) and str(anotacion).strip() != "":
            tag_name = "extra"
            extra_val = str(anotacion).strip()
        else:
            if tag_idx < len(tag_keys):
                tag_name = tag_keys[tag_idx]
                extra_val = tags[tag_name]
                tag_idx += 1
            else:
                print(f"Advertencia: No hay suficientes tags definidos en el diccionario para la fila {i}")
                continue

        rows_list.append({
            "id": row['id'],
            "tags_timestamp": row['tags_timestamp'],
            "tag": tag_name,
            "extra": extra_val
        })

    if tag_idx < len(tag_keys):
        print(f"Advertencia: solo se asignaron {tag_idx} de {len(tag_keys)} tags; "
              f"faltan {len(tag_keys) - tag_idx} (revisar tags_mod.csv).")

    tags_def = pd.DataFrame(rows_list)
    tags_def.to_csv(f"{ruta}/{id_completo}_tags.csv", index=False)
    print(f"Archivo tags.csv generado exitosamente en {ruta}")


def main():
    if len(sys.argv) < 5:
        print("Error: Faltan parámetros.")
        print("Uso correcto: python tags_def.py <center> <date> <id_num> <fase>")
        sys.exit(1)

    center = sys.argv[1]
    date = sys.argv[2]
    id_completo = center + "_" + sys.argv[3]
    fase = sys.argv[4]

    ruta = f"data/{fase}/{center}/{id_completo}-{date}"

    try:
        os.makedirs(ruta, exist_ok=True)
        print(f"Directorio creado o verificado correctamente: {ruta}")
    except Exception as e:
        print(f"Hubo un error al crear el directorio: {e}")
        sys.exit(1)

    try:
        tags_mod = pd.read_csv(f"{ruta}/{id_completo}_tags_mod.csv")
        extrae_tags(tags_mod, id_completo, ruta)
    except FileNotFoundError:
        print(f"Error: No se encontró el archivo tags_mod.csv en la ruta {ruta}")


if __name__ == "__main__":
    main()
