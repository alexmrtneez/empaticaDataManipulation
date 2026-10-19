# Empatica EmbracePlus data extraction and preparation for stress assessment

🇬🇧 English · [🇪🇸 Español](README_es.md)

A set of scripts to download, convert, segment and visualize the physiological data of
**Empatica EmbracePlus** wristbands in a stress-assessment study. Participants follow a protocol
of finding specific points of the **Parque de las Ciencias de Granada** (Spain). The protocol is run before
(`pre`) and after (`post`) the installation of accessible signage in the park.

> The code, comments, console messages and figure labels are in Spanish. This README
> describes them in English; the Spanish names are kept (in `code format`) so you can find them in the source.

## Study design

Each session uses **two wristbands**:

| Wristband | Worn by | What is used from it |
|---|---|---|
| Participant | The person being assessed | Physiological signals: EDA, pulse (derived from systolic peaks), accelerometer, temperature (+ BVP and steps) |
| Evaluator | The researcher | **Tags** only: the button is pressed at each milestone of the protocol |

Several people are assessed with the same wristband on a given day, so each participant is
later trimmed by their own time window. The full protocol (56 tags) is in `Plantilla.pdf`
("Plantilla" = template).

## Pipeline

```
dataDownload.sh ─► avroToCSV.py ─► separate_participant.py ─► (manual review) ─► tags_def.py ─► graficarTiempoFreq.py
   (S3 → AVRO)    (AVRO→CSV)    (per-participant trim)      tags_mod.csv     (final tags)       (figures)
```

| Step | Script | What it does |
|---|---|---|
| 1 | `dataDownload.sh` | Downloads the AVRO files of one wristband and one day from S3 using Cyberduck CLI (`duck`). |
| 2 | `avroToCSV.py` (+ `avro_utils.py`) | Converts the day's AVRO files into one CSV per sensor (`processed/`). Exports are commented/uncommented in `exportar_sensores()` depending on the wristband. |
| 3 | `separate_participant.py` | Trims the CSVs to one participant's time window; computes pulse rate (BPM) from systolic peaks; extracts the evaluator's tags into `tags_orig.csv` and `tags_mod.csv`. |
| 4 | *(manual)* | Review `tags_mod.csv`: if a tag noted on paper is missing, duplicate the previous row and adjust it; optionally fill an `anotacion` (annotation) column. |
| 5 | `tags_def.py` | Assigns a name to each tag by position and generates the final `<id>_tags.csv`. Rows with an `anotacion` are labelled `extra`. |
| 6 | `graficarTiempoFreq.py` | Generates the per-phase time-series figure and the per-phase, per-signal distribution figure (violin + boxplot). |

## Usage

```bash
pip install -r requirements.txt
# Also required: Cyberduck CLI (`duck`) for dataDownload.sh

export EMPATICA_S3_USER="<access key id>"
export EMPATICA_S3_BASE="s3://s3.amazonaws.com/<bucket>/v2/<org>/<study>/<site>/participant_data"

# 1. Download (once per wristband and day)
./dataDownload.sh 2026-05-15 HV        # participant's wristband
./dataDownload.sh 2026-05-15 FY        # evaluator's wristband

# 2. AVRO -> CSV  (edit FECHA and DISPOSITIVO in avroToCSV.py and enable the desired sensors)
python avroToCSV.py

# 3. Trim one participant: <center> <date> <participant dev> <evaluator dev> <id> <phase> <start> <end>
python separate_participant.py ECO 2026-05-15 HV FY 001 pre 10:32 11:10

# 4. Manually review data/pre/ECO/ECO_001-2026-05-15/ECO_001_tags_mod.csv

# 5. Final tags:  <center> <date> <id> <phase>
python tags_def.py ECO 2026-05-15 001 pre

# 6. Figures
python graficarTiempoFreq.py ECO 2026-05-15 001 pre
```

## Generated directory structure

```
cyberduck/<date>/<device>/raw/              downloaded AVRO files
cyberduck/<date>/<device>/processed/        whole-day CSVs, per sensor
data/<pre|post>/<center>/<center>_<id>-<date>/   participant CSVs, tags and figures
```

## Protocol phases (used in the figures)

Each phase is delimited by a pair of tags (see `configuracion_fases` in `graficarTiempoFreq.py`).

| Figure label | English | Start tag → end tag |
|---|---|---|
| Basal | Baseline | `ts_eav1_start` → `ts_sp_end` |
| Baño | Activity 1: Bathroom | `ts_inst_task1_start` → `ts_task1_end` |
| Biodomo | Activity 2: Biodome | `ts_inst_task2_start` → `ts_task2_end` |
| Mariposario | Activity 3: Butterfly house | `ts_inst_task3_start` → `ts_task3_end` |
| Salida | Activity 4: Exit | `ts_inst_task4_start` → `ts_task4_end` |
| Cuestionario posterior | Post-task questionnaire | `ts_eav2_start` → `ts_et_end` |
| Recuperación | Recovery | `ts_inst_bl_start` → `ts_eav3_end` |

## Example output (participant ECO_001)

![Time series](docs/ECO_001-2026-05-15_biometricos_fases.png)
![Distributions](docs/ECO_001-2026-05-15_distribucion_fases.png)

## Notes

* The `datetime_utc` columns in the CSVs are in the **local time of the machine** that ran
  `avroToCSV.py`, not strict UTC; the times given to `separate_participant.py` and the X axis of the
  figures use that same reference. The `unix_timestamp_*` columns are true Unix epoch values.
* Figure preprocessing: outlier removal by IQR (1.5·IQR) followed by linear interpolation;
  accelerometer shown as the Euclidean norm of the three axes.
* Tag names in `tags_def.py` differ slightly from some in `Plantilla.pdf` (e.g. `ts_stressvulnerability_*` = `ts_sv_*`);
  the names in the code are the ones used by the plotting script.
* Participant data (`cyberduck/`, `data/`) is excluded in `.gitignore`.