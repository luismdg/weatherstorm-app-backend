from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
import json, glob, os, time
from datetime import datetime

router = APIRouter()
# Obtener el directorio base del proyecto (donde está este archivo)
BASE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = BASE_DIR / "Data" / "Data"
print(f"DATA_DIR: {DATA_DIR}")

# --- CACHE SIMPLE ---
# Guardará las rutas a los directorios por 5 minutos (300 segundos)
LATEST_DIR_CACHE = {"path": None, "timestamp": 0}
DATE_DIR_CACHE = {}  # key: date, value: {"path": None, "timestamp": 0}
CACHE_TTL = 300  # 5 minutos


def parse_dirname_timestamp(dir_path):
    """Extrae timestamp del nombre: 20251103_114143 -> 20251103114143"""
    try:
        name = dir_path.name
        if "_" not in name or len(name) < 15:
            return 0
        timestamp_str = name.replace("_", "")
        return int(timestamp_str)
    except:
        return 0


# Al iniciar, mostrar info
@router.on_event("startup")
async def startup_event():
    print("=" * 60)
    print(f"DATA_DIR: {DATA_DIR.absolute()}")
    print(f"DATA_DIR existe: {DATA_DIR.exists()}")

    if DATA_DIR.exists():
        dirs = [d for d in DATA_DIR.glob("*") if d.is_dir()]
        print(f"\nDirectorios encontrados ({len(dirs)}):")

        # Mostrar solo los últimos 10
        for d in sorted(dirs)[-10:]:
            mtime = datetime.fromtimestamp(os.path.getmtime(d))
            print(f" {d.name} - modificado: {mtime}")

        if dirs:
            # USAR LA MISMA LÓGICA QUE get_latest_directory()
            latest = max(dirs, key=parse_dirname_timestamp)
            print(f"\n Directorio elegido como más reciente: {latest.name}")
            print(f"   Timestamp parseado: {parse_dirname_timestamp(latest)}")
    print("=" * 60)


def get_latest_directory():
    """Devuelve el directorio más reciente (AHORA CON CACHE)"""
    current_time = time.time()
    # 1. Verificar cache
    if LATEST_DIR_CACHE["path"] and (
        current_time - LATEST_DIR_CACHE["timestamp"] < CACHE_TTL
    ):
        return LATEST_DIR_CACHE["path"]

    # 2. Si no hay cache, escanear
    if not DATA_DIR.exists():
        return None
    dirs = [d for d in DATA_DIR.glob("*") if d.is_dir()]
    if not dirs:
        return None

    # 3. Calcular y guardar en cache
    latest = max(dirs, key=parse_dirname_timestamp)
    LATEST_DIR_CACHE["path"] = latest
    LATEST_DIR_CACHE["timestamp"] = current_time
    return latest


def get_directory_by_date(target_date: str):
    """Encuentra el directorio más reciente para una fecha (AHORA CON CACHE)"""
    current_time = time.time()
    # 1. Verificar cache para esta fecha
    if target_date in DATE_DIR_CACHE and (
        current_time - DATE_DIR_CACHE[target_date]["timestamp"] < CACHE_TTL
    ):
        return DATE_DIR_CACHE[target_date]["path"]

    # 2. Si no hay cache, escanear
    if not DATA_DIR.exists():
        return None
    matching_dirs = [
        dir_path for dir_path in DATA_DIR.glob(f"*{target_date}*") if dir_path.is_dir()
    ]

    # 3. Calcular y guardar en cache
    if not matching_dirs:
        DATE_DIR_CACHE[target_date] = {"path": None, "timestamp": current_time}
        return None

    latest_for_date = max(matching_dirs, key=parse_dirname_timestamp)
    DATE_DIR_CACHE[target_date] = {"path": latest_for_date, "timestamp": current_time}
    return latest_for_date


# --- NUEVA FUNCIÓN ---
def get_all_dirs_by_date(target_date: str):
    """Encuentra TODOS los directorios de una fecha, ordenados por timestamp."""
    if not DATA_DIR.exists():
        return []

    matching_dirs = [
        dir_path for dir_path in DATA_DIR.glob(f"*{target_date}*") if dir_path.is_dir()
    ]

    # Ordenar por el timestamp para que las imágenes salgan en orden
    return sorted(matching_dirs, key=parse_dirname_timestamp)


@router.get("/")
def root():
    return {"message": "API del Sistema de Monitoreo de Tormentas Tropicales"}


# RUTAS JSON =========================


@router.get("/storms")
def get_all_storms():
    """Devuelve el JSON general más reciente (todas las tormentas)."""
    latest_dir = get_latest_directory()
    if not latest_dir:
        raise HTTPException(status_code=404, detail="No hay datos generados aún.")

    json_dir = latest_dir / "JSON"
    json_files = sorted(json_dir.glob("tormentas*.json"))
    if not json_files:
        raise HTTPException(status_code=404, detail="No se encontró el JSON general.")

    latest_json = json_files[-1]
    with open(latest_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    return JSONResponse(content=data)


@router.get("/storms/{storm_id}")
def get_single_storm(storm_id: str):
    """Devuelve el JSON individual de una tormenta específica."""
    latest_dir = get_latest_directory()
    if not latest_dir:
        raise HTTPException(status_code=404, detail="No hay datos generados aún.")

    json_path = latest_dir / "JSON" / f"tormenta_{storm_id}.json"
    if not json_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No se encontró el archivo JSON de la tormenta {storm_id}.",
        )

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return JSONResponse(content=data)


@router.get("/date/{date}/storms")
def get_storms_by_date(date: str):
    """Devuelve todos los JSON de una fecha específica."""
    target_dir = get_directory_by_date(date)
    if not target_dir:
        raise HTTPException(
            status_code=404, detail=f"No se encontraron datos para la fecha: {date}"
        )

    json_dir = target_dir / "JSON"
    if not json_dir.exists():
        raise HTTPException(
            status_code=404, detail="No se encontró la carpeta JSON para esta fecha."
        )

    json_files = list(json_dir.glob("*.json"))
    if not json_files:
        raise HTTPException(
            status_code=404, detail="No se encontraron archivos JSON para esta fecha."
        )

    all_data = {}
    for json_file in json_files:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                all_data[json_file.stem] = json.load(f)
        except Exception as e:
            all_data[json_file.stem] = {
                "error": f"No se pudo cargar el archivo: {str(e)}"
            }

    return JSONResponse(
        content={
            "date": date,
            "directory": target_dir.name,
            "total_files": len(json_files),
            "data": all_data,
        }
    )


@router.get("/date/{date}/storms/{storm_id}")
def get_storm_by_date_and_id(date: str, storm_id: str):
    """Devuelve el archivo JSON de una tormenta específica en una fecha específica."""
    target_dir = get_directory_by_date(date)
    if not target_dir:
        raise HTTPException(
            status_code=404, detail=f"No se encontraron datos para la fecha: {date}"
        )

    json_dir = target_dir / "JSON"
    if not json_dir.exists():
        raise HTTPException(
            status_code=404, detail="No se encontró la carpeta JSON para esta fecha."
        )

    json_path = json_dir / f"tormenta_{storm_id}.json"
    if not json_path.exists():
        json_files = list(json_dir.glob(f"*{storm_id}*.json"))
        if not json_files:
            raise HTTPException(
                status_code=404,
                detail=f"No se encontró el archivo JSON de la tormenta {storm_id} para la fecha {date}.",
            )
        json_path = json_files[0]

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return JSONResponse(
        content={
            "date": date,
            "storm_id": storm_id,
            "file": json_path.name,
            "data": data,
        }
    )


# RUTAS MAPAS =========================


@router.get("/maps")
def get_general_map():
    """Devuelve el mapa general más reciente con todas las tormentas."""
    latest_dir = get_latest_directory()
    if not latest_dir:
        raise HTTPException(status_code=404, detail="No hay mapas generados aún.")

    map_dir = latest_dir / "Mapas"
    map_files = sorted(map_dir.glob("mapa_*.png"))
    if not map_files:
        raise HTTPException(status_code=404, detail="No se encontró el mapa general.")

    latest_map = map_files[-1]
    return FileResponse(latest_map, media_type="image/png")


@router.get("/maps/{storm_id}")
def get_storm_map(storm_id: str):
    """Devuelve el mapa individual de una tormenta específica mas reciente."""
    latest_dir = get_latest_directory()
    if not latest_dir:
        raise HTTPException(status_code=404, detail="No hay mapas generados aún.")

    map_path = latest_dir / "Mapas" / f"{storm_id}.png"
    if not map_path.exists():
        raise HTTPException(
            status_code=404, detail=f"No se encontró el mapa de la tormenta {storm_id}."
        )

    return FileResponse(map_path, media_type="image/png")


# NUEVAS RUTAS PARA OBTENER METADATA DE IMÁGENES
# (Estas rutas usan 'glob' recursivo y pueden ser lentas)
# (Sería ideal optimizarlas si la lentitud persiste)


@router.get("/date/{date}/maps/general/list")
def get_all_general_maps_metadata_by_date(date: str):
    """
    Devuelve una lista con índices de todas las imágenes PNG (mapa_*.png)
    para poder accederlas individualmente.
    ¡ARREGLADO! Ahora busca en TODOS los directorios de esa fecha.
    """
    all_dirs = get_all_dirs_by_date(date)
    if not all_dirs:
        raise HTTPException(
            status_code=404, detail=f"No se encontraron datos para la fecha {date}."
        )

    all_image_paths = []
    for dir_path in all_dirs:
        map_dir = dir_path / "Mapas"
        if map_dir.exists():
            # Añadimos todos los mapas encontrados, ya ordenados por nombre de archivo
            all_image_paths.extend(sorted(map_dir.glob("mapa_*.png")))

    if not all_image_paths:
        raise HTTPException(
            status_code=404, detail=f"No se encontraron mapas para la fecha {date}."
        )

    return {
        "date": date,
        "total_images": len(all_image_paths),
        "images": [
            {"index": i, "filename": path.name}
            for i, path in enumerate(all_image_paths)
        ],
    }


@router.get("/date/{date}/maps/general/{index}")
def get_general_map_by_date_and_index(date: str, index: int):
    """
    Devuelve la imagen PNG del mapa general en la posición 'index' para la fecha dada.
    ¡ARREGLADO! Ahora busca en TODOS los directorios de esa fecha.
    """
    all_dirs = get_all_dirs_by_date(date)
    if not all_dirs:
        raise HTTPException(
            status_code=404, detail=f"No se encontraron datos para la fecha {date}."
        )

    all_image_paths = []
    for dir_path in all_dirs:
        map_dir = dir_path / "Mapas"
        if map_dir.exists():
            all_image_paths.extend(sorted(map_dir.glob("mapa_*.png")))

    if not all_image_paths:
        raise HTTPException(
            status_code=404, detail=f"No se encontraron mapas para la fecha {date}."
        )

    if index < 0 or index >= len(all_image_paths):
        raise HTTPException(
            status_code=404,
            detail=f"Índice {index} fuera de rango. Total de imágenes: {len(all_image_paths)}",
        )

    return FileResponse(all_image_paths[index], media_type="image/png")


@router.get("/date/{date}/maps/{storm_id}/list")
def get_storm_maps_metadata_by_date(date: str, storm_id: str):
    """
    Devuelve una lista con índices de todas las imágenes PNG del storm_id
    para poder accederlas individualmente.
    ¡ARREGLADO! Ahora busca en TODOS los directorios de esa fecha.
    """
    all_dirs = get_all_dirs_by_date(date)
    if not all_dirs:
        raise HTTPException(
            status_code=404, detail=f"No se encontraron datos para la fecha {date}."
        )

    all_image_paths = []
    for dir_path in all_dirs:
        map_dir = dir_path / "Mapas"
        if map_dir.exists():
            all_image_paths.extend(sorted(map_dir.glob(f"*{storm_id}*.png")))

    if not all_image_paths:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontraron mapas del storm_id '{storm_id}' para la fecha {date}.",
        )

    return {
        "date": date,
        "storm_id": storm_id,
        "total_images": len(all_image_paths),
        "images": [
            {"index": i, "filename": path.name}
            for i, path in enumerate(all_image_paths)
        ],
    }


@router.get("/date/{date}/maps/{storm_id}/{index}")
def get_storm_map_by_date_and_index(date: str, storm_id: str, index: int):
    """
    Devuelve la imagen PNG del storm_id en la posición 'index' para la fecha dada.
    ¡ARREGLADO! Ahora busca en TODOS los directorios de esa fecha.
    """
    all_dirs = get_all_dirs_by_date(date)
    if not all_dirs:
        raise HTTPException(
            status_code=404, detail=f"No se encontraron datos para la fecha {date}."
        )

    all_image_paths = []
    for dir_path in all_dirs:
        map_dir = dir_path / "Mapas"
        if map_dir.exists():
            all_image_paths.extend(sorted(map_dir.glob(f"*{storm_id}*.png")))

    if not all_image_paths:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontraron mapas del storm_id '{storm_id}' para la fecha {date}.",
        )

    if index < 0 or index >= len(all_image_paths):
        raise HTTPException(
            status_code=404,
            detail=f"Índice {index} fuera de rango. Total de imágenes: {len(all_image_paths)}",
        )

    return FileResponse(all_image_paths[index], media_type="image/png")
