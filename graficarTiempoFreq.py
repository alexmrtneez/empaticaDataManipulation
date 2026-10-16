"""
graficarTiempoFreq.py
=====================
Paso 5 del pipeline: genera las dos figuras de un participante.

  1. ``<id>-<fecha>_biometricos_fases.png``  Series temporales de cada señal (EDA, pulso,
     acelerómetro [norma], temperatura) con las fases del protocolo sombreadas y los tags
     "extra" (anotaciones del evaluador) como líneas rojas discontinuas.
  2. ``<id>-<fecha>_distribucion_fases.png`` Distribución de cada señal en cada fase
     (violin plot + boxplot), una columna por fase y una fila por señal.

Entrada (carpeta del participante, generada por separate_participant.py y tags_def.py):
    <id>_eda.csv, <id>_pulse_rate.csv, <id>_accelerometer.csv, <id>_temperature.csv, <id>_tags.csv

Preprocesado de cada señal (cargar_datos_empatica):
    1. Relleno de huecos al inicio/final (ffill + bfill).
    2. Outliers fuera de [Q1 - 1.5·IQR, Q3 + 1.5·IQR] -> NaN -> interpolación lineal.
       (Se aplica a cada columna por separado; en el acelerómetro, a cada eje.)
    3. Acelerómetro: se calcula la norma euclídea sqrt(x² + y² + z²).

Las fases se delimitan con pares de tags (ver ``configuracion_fases``). Los tags del
archivo tags.csv se convierten de µs a s para compararlos con las señales.

Uso:
    python graficarTiempoFreq.py <center> <fecha> <id> <fase>
    python graficarTiempoFreq.py ECO 2026-05-15 001 pre
"""

import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns


def cargar_datos_empatica(ruta_archivo):
    """
    Carga y limpia un CSV de señal biométrica.

    Detecta el tipo de señal por sus columnas:
      * acelerómetro (``x_g``, ``y_g``, ``z_g``): devuelve los 3 ejes y la columna ``norma``.
      * EDA, pulso o temperatura: toma la última columna del CSV como valor -> columna ``valor``.
    El timestamp puede venir en microsegundos (``unix_timestamp_micros``) o nanosegundos
    (``unix_timestamp_nanos``).

    Returns:
        DataFrame con ``timestamp`` (s, Unix epoch), ``datetime`` y las columnas de valor;
        None si el archivo no existe o no tiene columna de timestamp reconocible.
    """
    if not os.path.exists(ruta_archivo):
        print(f"Advertencia: No se encontró el archivo {ruta_archivo}")
        return None

    df = pd.read_csv(ruta_archivo)

    if 'unix_timestamp_micros' in df.columns:
        timestamp_col = 'unix_timestamp_micros'
        divisor = 1e6
    elif 'unix_timestamp_nanos' in df.columns:
        timestamp_col = 'unix_timestamp_nanos'
        divisor = 1e9
    else:
        print(f"Advertencia: No se encontraron columnas de timestamp esperadas en {ruta_archivo}")
        return None

    es_acelerometro = 'x_g' in df.columns
    cols_valores = ['x_g', 'y_g', 'z_g'] if es_acelerometro else [df.columns[-1]]

    timestamps_seg = df[timestamp_col] / divisor

    resultado = pd.DataFrame({
        'timestamp': timestamps_seg,
        'datetime': pd.to_datetime(timestamps_seg, unit='s', utc=True)
    })

    for col in cols_valores:
        valores = df[col].ffill().bfill()

        # Detección de outliers por rango intercuartílico (IQR)
        Q1 = valores.quantile(0.25)
        Q3 = valores.quantile(0.75)
        IQR = Q3 - Q1
        limite_inferior = Q1 - 1.5 * IQR
        limite_superior = Q3 + 1.5 * IQR

        valores_sin_outliers = valores.copy()
        outliers_mask = (valores < limite_inferior) | (valores > limite_superior)
        valores_sin_outliers[outliers_mask] = np.nan

        valores = valores_sin_outliers.interpolate(method='linear').ffill().bfill()

        if es_acelerometro:
            resultado[col] = valores
        else:
            resultado['valor'] = valores

    if es_acelerometro:
        resultado['norma'] = np.sqrt(resultado['x_g']**2 + resultado['y_g']**2 + resultado['z_g']**2)
        print(f"  Acelerómetro cargado. Rango norma: [{resultado['norma'].min():.2f}, {resultado['norma'].max():.2f}]")
    else:
        print(f"  Datos cargados. Rango válido: [{limite_inferior:.2f}, {limite_superior:.2f}]")

    return resultado


def cargar_tags(ruta_tags):
    """
    Carga ``<id>_tags.csv`` (salida de tags_def.py) y añade ``timestamp_seg``
    (``tags_timestamp`` de µs a s).
    """
    df_tags = pd.read_csv(ruta_tags)
    df_tags['timestamp_seg'] = df_tags['tags_timestamp'] / 1e6
    return df_tags


def generar_grafico_distribucion(datos_señales, fases_calculadas, participant_dir, id_completo, fecha):
    """
    Figura de distribuciones: una fila por señal y una columna por fase, con violin plot
    (densidad) y boxplot (mediana, cuartiles y bigotes) superpuestos. El eje Y se
    comparte por fila para poder comparar fases. Para el acelerómetro se usa la norma.

    Args:
        datos_señales (dict): {nombre_señal: DataFrame} devuelto por generar_grafico_biometrico.
        fases_calculadas (list): fases con 'nombre', 'inicio', 'fin' (s) y 'color'.
        participant_dir (str): carpeta donde se guarda el PNG.
    """
    print("\nGenerando gráfico de distribución por fases...")

    datos_lista = []
    for metrica, df in datos_señales.items():
        es_acelerometro = 'x_g' in df.columns

        for fase in fases_calculadas:
            mascara = (df['timestamp'] >= fase['inicio']) & (df['timestamp'] <= fase['fin'])
            df_fase = df[mascara].copy()

            if not df_fase.empty:
                df_fase['Metrica'] = metrica
                df_fase['Fase'] = fase['nombre']
                df_fase['Color'] = fase['color']
                df_fase['valor_grafico'] = df_fase['norma'] if es_acelerometro else df_fase['valor']
                datos_lista.append(df_fase)

    if not datos_lista:
        print("No hay datos cruzados con fases para generar distribuciones.")
        return

    df_dist = pd.concat(datos_lista, ignore_index=True)

    metricas = list(datos_señales.keys())
    fases_presentes = [f['nombre'] for f in fases_calculadas if f['nombre'] in df_dist['Fase'].unique()]
    colores = {f['nombre']: f['color'] for f in fases_calculadas}

    fig, axes = plt.subplots(nrows=len(metricas), ncols=len(fases_presentes),
                             figsize=(3.5 * len(fases_presentes), 4 * len(metricas)),
                             sharey='row')

    # plt.subplots devuelve un array 1D si hay una sola fila o columna: se fuerza a 2D
    if len(metricas) == 1 and len(fases_presentes) == 1:
        axes = np.array([[axes]])
    elif len(metricas) == 1:
        axes = axes[np.newaxis, :]
    elif len(fases_presentes) == 1:
        axes = axes[:, np.newaxis]

    for r, metrica in enumerate(metricas):
        for c, fase_nombre in enumerate(fases_presentes):
            ax = axes[r, c]
            df_sub = df_dist[(df_dist['Metrica'] == metrica) & (df_dist['Fase'] == fase_nombre)]

            if not df_sub.empty:
                color = colores[fase_nombre]
                sns.violinplot(y='valor_grafico', data=df_sub, ax=ax, color=color, inner=None, linewidth=0, alpha=0.4)
                sns.boxplot(y='valor_grafico', data=df_sub, ax=ax, width=0.15, color='white', showfliers=False, zorder=2)

            if r == 0:
                ax.set_title(fase_nombre, fontweight='bold', fontsize=11, pad=15)

            if c == 0:
                ax.set_ylabel(metrica, fontweight='bold')
            else:
                ax.set_ylabel('')

            ax.set_xticks([])
            ax.set_xlabel('')
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['bottom'].set_visible(False)
            ax.grid(axis='y', linestyle='-', alpha=0.2)

    fig.suptitle(f'Distribución de la actividad fisiológica por fases - {id_completo}',
                 fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()

    ruta_figura = os.path.join(participant_dir, f'{id_completo}-{fecha}_distribucion_fases.png')
    plt.savefig(ruta_figura, dpi=300, bbox_inches='tight')
    print(f"Gráfico de distribución guardado en: {ruta_figura}")


def generar_grafico_biometrico(config_archivos, ruta_tags, fases_config, participant_dir, id_completo, fecha):
    """
    Figura multipanel de series temporales (un panel por señal, eje X compartido),
    limitada al intervalo que va del inicio de la primera fase al fin de la última.

    Args:
        config_archivos (dict): {etiqueta del panel: ruta del CSV}.
        ruta_tags (str): ruta de ``<id>_tags.csv``.
        fases_config (list): fases con 'nombre', 'tag_inicio', 'tag_fin' y 'color'.
        participant_dir, id_completo, fecha: para nombrar y ubicar el PNG.

    Returns:
        tuple: (datos_señales, fases_calculadas) para reutilizar en la figura de
               distribuciones, o (None, None) si no hay datos o fases.
    """
    datos_señales = {}
    for metric, ruta in config_archivos.items():
        df = cargar_datos_empatica(ruta)
        if df is not None:
            datos_señales[metric] = df

    if not datos_señales:
        print("No hay datos disponibles para graficar.")
        return None, None

    df_tags = cargar_tags(ruta_tags)

    # Traducir cada fase (par de tags) a un intervalo de tiempo en segundos
    fases_calculadas = []
    for fase in fases_config:
        t_start_row = df_tags[df_tags['tag'] == fase['tag_inicio']]
        t_end_row = df_tags[df_tags['tag'] == fase['tag_fin']]

        if not t_start_row.empty and not t_end_row.empty:
            fases_calculadas.append({
                'nombre': fase['nombre'],
                'inicio': t_start_row['timestamp_seg'].values[0],
                'fin': t_end_row['timestamp_seg'].values[0],
                'color': fase.get('color', '#dddddd')
            })
        else:
            print(f"Aviso: No se pudo mapear la fase '{fase['nombre']}'.")

    if fases_calculadas:
        tiempo_inicio = fases_calculadas[0]['inicio']
        tiempo_fin = fases_calculadas[-1]['fin']
        print(f"\nGraficando series temporales desde {tiempo_inicio:.0f} hasta {tiempo_fin:.0f}")
    else:
        print("No hay fases activas para graficar.")
        return None, None

    num_metricas = len(datos_señales)
    fig, axes = plt.subplots(nrows=num_metricas, ncols=1, figsize=(14, 4 * num_metricas), sharex=True)

    if num_metricas == 1:
        axes = [axes]

    fig.suptitle(f'Datos Biométricos - {id_completo} ({fecha})', fontsize=14, fontweight='bold', y=0.995)

    for i, (nombre_metrica, df) in enumerate(datos_señales.items()):
        ax = axes[i]
        df_filtrado = df[(df['timestamp'] >= tiempo_inicio) & (df['timestamp'] <= tiempo_fin)]

        if 'x_g' in df.columns:  # acelerómetro: se dibuja solo la norma
            ax.plot(df_filtrado['timestamp'], df_filtrado['norma'], label='Norma', color='#2c3e50', linewidth=1)
        else:
            ax.plot(df_filtrado['timestamp'], df_filtrado['valor'], label=nombre_metrica, color='#2c3e50', linewidth=1.5)

        ax.set_ylabel(nombre_metrica, fontsize=11, fontweight='bold')
        ax.grid(True, linestyle='--', alpha=0.5)

        for fase in fases_calculadas:
            ax.axvspan(fase['inicio'], fase['fin'], color=fase['color'], alpha=0.3, label=fase['nombre'])

        # Anotaciones manuales del evaluador (tags "extra")
        for _, fila in df_tags[df_tags['tag'] == 'extra'].iterrows():
            ax.axvline(x=fila['timestamp_seg'], color='#d90429', linestyle='--', linewidth=1.5, alpha=0.8)

    # Leyenda: solo las fases, sin duplicados
    handles, labels = axes[0].get_legend_handles_labels()
    fase_labels = []
    fase_handles = []
    for handle, label in zip(handles, labels):
        es_fase = any(f['nombre'] == label for f in fases_calculadas)
        if label and label not in fase_labels and es_fase:
            fase_labels.append(label)
            fase_handles.append(handle)

    axes[0].legend(fase_handles, fase_labels, loc='upper left', fontsize=10, title='Fases')

    # Marcas del eje X: inicio y fin de cada fase, descartando las separadas menos de 30 s
    ticks_fases = sorted({t for fase in fases_calculadas for t in (fase['inicio'], fase['fin'])})
    ticks_filtrados = []
    ultimo_t = None
    for t in ticks_fases:
        if ultimo_t is None or (t - ultimo_t) > 30:
            ticks_filtrados.append(t)
            ultimo_t = t

    axes[-1].set_xticks(ticks_filtrados)

    def unix_to_readable(x, pos):
        # Hora local del equipo (coherente con datetime_utc de avro_utils.py)
        return datetime.fromtimestamp(x).strftime('%H:%M')

    axes[-1].xaxis.set_major_formatter(plt.FuncFormatter(unix_to_readable))
    plt.setp(axes[-1].get_xticklabels(), rotation=45, ha='right', fontsize=9)
    axes[-1].set_xlabel("Tiempo (HH:MM)", fontsize=12)
    axes[-1].set_xlim(tiempo_inicio, tiempo_fin)

    plt.tight_layout()

    ruta_figura = os.path.join(participant_dir, f'{id_completo}-{fecha}_biometricos_fases.png')
    plt.savefig(ruta_figura, dpi=300, bbox_inches='tight')
    print(f"Gráfico de series guardado en: {ruta_figura}")

    return datos_señales, fases_calculadas


if __name__ == "__main__":
    try:
        center = sys.argv[1]
        fecha = sys.argv[2]
        id_completo = center + "_" + sys.argv[3]
        fase = sys.argv[4]
    except IndexError:
        print("Error: Faltan argumentos. Uso: python graficarTiempoFreq.py <center> <fecha> <id> <fase>")
        sys.exit(1)

    participant_dir = f"./data/{fase}/{center}/{id_completo}-{fecha}"

    # Señales a mostrar (un panel/fila por entrada). Comentar las que no se necesiten.
    archivos_biometricos = {
        'EDA (μS)': f"{participant_dir}/{id_completo}_eda.csv",
        'Pulse (BPM)': f"{participant_dir}/{id_completo}_pulse_rate.csv",
        'Accelerometer (g)': f"{participant_dir}/{id_completo}_accelerometer.csv",
        'Temperature (ºC)': f"{participant_dir}/{id_completo}_temperature.csv"
    }

    archivo_tags = f"{participant_dir}/{id_completo}_tags.csv"

    # Fases del protocolo: cada una va del tag de inicio al tag de fin.
    configuracion_fases = [
        {'nombre': 'Basal', 'tag_inicio': 'ts_eav1_start', 'tag_fin': 'ts_sp_end', 'color': '#a8dadc'},
        {'nombre': 'Baño', 'tag_inicio': 'ts_inst_task1_start', 'tag_fin': 'ts_task1_end', 'color': "#d6e0d3"},
        {'nombre': 'Biodomo', 'tag_inicio': 'ts_inst_task2_start', 'tag_fin': 'ts_task2_end', 'color': "#5eef2e"},
        {'nombre': 'Mariposario', 'tag_inicio': 'ts_inst_task3_start', 'tag_fin': 'ts_task3_end', 'color': '#e9c46a'},
        {'nombre': 'Salida', 'tag_inicio': 'ts_inst_task4_start', 'tag_fin': 'ts_task4_end', 'color': "#e96a6a"},
        {'nombre': 'Cuestionario posterior', 'tag_inicio': 'ts_eav2_start', 'tag_fin': 'ts_et_end', 'color': "#6ae9e7"},
        {'nombre': 'Recuperación', 'tag_inicio': 'ts_inst_bl_start', 'tag_fin': 'ts_eav3_end', 'color': "#e96ac3"}
    ]

    datos_señales, fases_calculadas = generar_grafico_biometrico(
        archivos_biometricos, archivo_tags, configuracion_fases,
        participant_dir, id_completo, fecha
    )

    if datos_señales and fases_calculadas:
        generar_grafico_distribucion(
            datos_señales, fases_calculadas, participant_dir, id_completo, fecha
        )
