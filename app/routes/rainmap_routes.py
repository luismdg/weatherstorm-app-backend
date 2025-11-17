from fastapi import APIRouter
from fastapi.responses import JSONResponse
import numpy as np, requests, concurrent.futures, time
import traceback

router = APIRouter()

# Default Cities Coordinates
MEXICAN_CITIES = [
    {"name": "Ciudad de Mexico", "lat": 19.4326, "lon": -99.1332, "state": "CDMX"},
    {"name": "Guadalajara", "lat": 20.6597, "lon": -103.3496, "state": "Jalisco"},
    {"name": "Monterrey", "lat": 25.6866, "lon": -100.3161, "state": "Nuevo León"},
    {"name": "Puebla", "lat": 19.0414, "lon": -98.2063, "state": "Puebla"},
    {"name": "Tijuana", "lat": 32.5149, "lon": -117.0382, "state": "Baja California"},
    {"name": "León", "lat": 21.1236, "lon": -101.676, "state": "Guanajuato"},
    {"name": "Juárez", "lat": 31.6904, "lon": -106.4245, "state": "Chihuahua"},
    {"name": "Zapopan", "lat": 20.7214, "lon": -103.3918, "state": "Jalisco"},
    {"name": "Mérida", "lat": 20.9674, "lon": -89.5926, "state": "Yucatán"},
    {
        "name": "San Luis Potosí",
        "lat": 22.1565,
        "lon": -100.9855,
        "state": "San Luis Potosí",
    },
    {
        "name": "Aguascalientes",
        "lat": 21.8853,
        "lon": -102.2916,
        "state": "Aguascalientes",
    },
    {"name": "Hermosillo", "lat": 29.0729, "lon": -110.9559, "state": "Sonora"},
    {"name": "Saltillo", "lat": 25.4232, "lon": -100.9737, "state": "Coahuila"},
    {"name": "Mexicali", "lat": 32.6245, "lon": -115.4523, "state": "Baja California"},
    {"name": "Culiacán", "lat": 24.8091, "lon": -107.394, "state": "Sinaloa"},
    {"name": "Querétaro", "lat": 20.5888, "lon": -100.3899, "state": "Querétaro"},
    {"name": "Chihuahua", "lat": 28.6353, "lon": -106.0889, "state": "Chihuahua"},
    {"name": "Morelia", "lat": 19.706, "lon": -101.1949, "state": "Michoacán"},
    {"name": "Toluca", "lat": 19.2827, "lon": -99.6557, "state": "Estado de México"},
    {"name": "Cancún", "lat": 21.1619, "lon": -86.8515, "state": "Quintana Roo"},
    {"name": "Acapulco", "lat": 16.8531, "lon": -99.8237, "state": "Guerrero"},
    {"name": "Torreón", "lat": 25.5428, "lon": -103.4068, "state": "Coahuila"},
    {"name": "Reynosa", "lat": 26.0922, "lon": -98.2777, "state": "Tamaulipas"},
    {"name": "Tuxtla Gutiérrez", "lat": 16.7516, "lon": -93.1029, "state": "Chiapas"},
    {"name": "Veracruz", "lat": 19.1738, "lon": -96.1342, "state": "Veracruz"},
    {"name": "Mazatlán", "lat": 23.2494, "lon": -106.4111, "state": "Sinaloa"},
    {"name": "Durango", "lat": 24.0277, "lon": -104.6532, "state": "Durango"},
    {"name": "Oaxaca", "lat": 17.0732, "lon": -96.7266, "state": "Oaxaca"},
    {"name": "Tampico", "lat": 22.2331, "lon": -97.8611, "state": "Tamaulipas"},
    {"name": "Irapuato", "lat": 20.6767, "lon": -101.3542, "state": "Guanajuato"},
    {"name": "Celaya", "lat": 20.5289, "lon": -100.8157, "state": "Guanajuato"},
    {"name": "Cuernavaca", "lat": 18.9211, "lon": -99.2378, "state": "Morelos"},
]
cityPoints = [{"lat": city["lat"], "lon": city["lon"]} for city in MEXICAN_CITIES]


# --- 1. Generate grid points ---
def generate_grid(grid_size=15):
    min_lon, max_lon, min_lat, max_lat = -118, -86.5, 14.5, 32.75
    lon = np.linspace(min_lon, max_lon, grid_size)
    lat = np.linspace(min_lat, max_lat, grid_size)
    points = [{"lat": float(a), "lon": float(b)} for a in lat for b in lon]
    points.extend(cityPoints)
    return points


# --- 2. Fetch single weather point ---
def fetch_point(p):
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": p["lat"],
                "longitude": p["lon"],
                "current": "precipitation",
            },
            timeout=3000,
        )
        r.raise_for_status()
        d = r.json().get("current", {})
        return {
            "lat": p["lat"],
            "lon": p["lon"],
            "precipitation": d.get("precipitation", 0),
        }
    except Exception as e:
        print("ERROR EN /rainmap/realtime:", traceback.format_exc())
        return JSONResponse(
            status_code=500, content={"detail": f"Internal Error: {str(e)}"}
        )
    except Exception as e:
        print("ERROR EN /rainmap/realtime:")
        print(traceback.format_exc())  # <-- prints the full traceback
        return JSONResponse(
            status_code=500, content={"detail": f"Internal Server Error: {str(e)}"}
        )


# --- 3. Parallel fetch all data ---
def get_weather(grid_size=15):
    pts = generate_grid(grid_size)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        data = list(ex.map(fetch_point, pts))
    return data


# --- 4. Haversine distance ---
def haversine(lat1, lon1, lats2, lons2):
    lat1, lon1, lats2, lons2 = map(np.radians, [lat1, lon1, lats2, lons2])
    a = (
        np.sin((lats2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lats2) * np.sin((lons2 - lon1) / 2) ** 2
    )
    return 6371 * 2 * np.arcsin(np.sqrt(a))


# --- 5. IDW interpolation ---
def idw(lat, lon, known_lats, known_lons, known_vals, power=2):
    d = haversine(lat, lon, known_lats, known_lons)
    d[d == 0] = 1e-6
    w = 1 / d**power
    return np.sum(w * known_vals) / np.sum(w)


# --- 6. Interpolate grid ---
def interpolate(data, density=100):
    lats = np.array([p["lat"] for p in data])
    lons = np.array([p["lon"] for p in data])
    vals = np.array([p["precipitation"] for p in data])
    latg = np.linspace(lats.min(), lats.max(), density)
    long = np.linspace(lons.min(), lons.max(), density)
    lat_grid, lon_grid = np.meshgrid(latg, long)
    interp_vals = np.zeros_like(lat_grid)
    for i in range(lat_grid.shape[0]):
        for j in range(lat_grid.shape[1]):
            interp_vals[i, j] = idw(lat_grid[i, j], lon_grid[i, j], lats, lons, vals)
    return [
        {
            "lat": float(lat_grid[i, j]),
            "lon": float(lon_grid[i, j]),
            "precipitation": float(interp_vals[i, j]),
        }
        for i in range(lat_grid.shape[0])
        for j in range(lat_grid.shape[1])
    ]


# --- 7. Real-time generator ---
def generate_real_time_json(grid_size=15, density=100):
    data = get_weather(grid_size)
    interp = interpolate(data, density)
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "original_points": len(data),
        "interpolated_points": len(interp),
        "data": interp,
    }


# === 8. FastAPI Interpolated Grid Route ====
@router.get("/realtime")
async def get_real_time_rainmap(grid_size: int = 15, density: int = 50):
    """
    Returns real-time interpolated precipitation data as JSON.
    Example: GET /rainmap/realtime?grid_size=10&density=40
    """
    try:
        result = generate_real_time_json(grid_size, density)
        return JSONResponse(content=result)
    except Exception as e:
        print("ERROR inside /rainmap/realtime:")
        print(traceback.format_exc())  # full traceback, line-by-line
        return JSONResponse(
            status_code=500,
            content={"error": "Internal Server Error", "detail": str(e)},
        )


# === 9. FastAPI MEXICAN CITIES Route ===
@router.get("/city")
async def get_mexican_cities(selectedCity: str = "Ciudad de Mexico"):
    """
    Returns precipitation data from specific cities
    """
    try:
        # Find the city directly
        city = next((c for c in MEXICAN_CITIES if c["name"] == selectedCity), None)

        if not city:
            return JSONResponse(
                status_code=404, content={"error": f"City '{selectedCity}' not found"}
            )

        # Fetch precipitation
        data = fetch_point({"lat": city["lat"], "lon": city["lon"]})
        return JSONResponse(content=data)

    except Exception as e:
        print("ERROR inside /rainmap/city:")
        print(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={"error": "Internal Server Error", "detail": str(e)},
        )
