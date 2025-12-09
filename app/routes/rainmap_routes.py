from fastapi import APIRouter
from fastapi.responses import JSONResponse
import numpy as np, requests, concurrent.futures, time
import traceback
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# Default Cities Coordinates (same as before)
MEXICAN_CITIES = [
    {"name": "Ciudad de Mexico", "lat": 19.4326, "lon": -99.1332, "state": "CDMX"},
    # ... rest of your cities
]
cityPoints = [{"lat": city["lat"], "lon": city["lon"]} for city in MEXICAN_CITIES]

# --- Configure requests session with retries ---
def create_session():
    # Configure retry strategy
    retry_strategy = Retry(
        total=3,  # Total retries
        backoff_factor=1,  # Wait 1, 2, 4 seconds between retries
        status_forcelist=[429, 500, 502, 503, 504],  # Retry on these status codes
        allowed_methods=["GET"]
    )
    
    # Create session
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # Set headers
    session.headers.update({
        'User-Agent': 'WeatherApp/1.0',
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip, deflate'
    })
    
    return session

# Create a global session
session = create_session()

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
        # Use the configured session
        r = session.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": p["lat"],
                "longitude": p["lon"],
                "current": "precipitation",
                "timezone": "auto"
            },
            timeout=10  # Reduced timeout from 3000 to 10 seconds
        )
        r.raise_for_status()
        d = r.json().get("current", {})
        
        # Log successful fetch
        logger.info(f"Fetched point: {p['lat']}, {p['lon']} - Precipitation: {d.get('precipitation', 0)}")
        
        return {
            "lat": p["lat"],
            "lon": p["lon"],
            "precipitation": d.get("precipitation", 0),
        }
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout for point {p['lat']}, {p['lon']}")
        return {
            "lat": p["lat"],
            "lon": p["lon"],
            "precipitation": 0,  # Default to 0 on timeout
        }
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed for point {p['lat']}, {p['lon']}: {str(e)}")
        return {
            "lat": p["lat"],
            "lon": p["lon"],
            "precipitation": 0,  # Default to 0 on error
        }
    except Exception as e:
        logger.error(f"Unexpected error for point {p['lat']}, {p['lon']}: {str(e)}")
        return {
            "lat": p["lat"],
            "lon": p["lon"],
            "precipitation": 0,  # Default to 0 on unexpected error
        }

# --- 3. Parallel fetch all data ---
def get_weather(grid_size=15):
    pts = generate_grid(grid_size)
    logger.info(f"Fetching weather for {len(pts)} points")
    
    # Reduce number of workers to avoid overwhelming the API
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        data = list(ex.map(fetch_point, pts))
    
    logger.info(f"Successfully fetched {len([d for d in data if d['precipitation'] != 0])} points with precipitation")
    return data

# --- Haversine and IDW functions (same as before) ---
def haversine(lat1, lon1, lats2, lons2):
    lat1, lon1, lats2, lons2 = map(np.radians, [lat1, lon1, lats2, lons2])
    a = (
        np.sin((lats2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lats2) * np.sin((lons2 - lon1) / 2) ** 2
    )
    return 6371 * 2 * np.arcsin(np.sqrt(a))

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
        logger.info(f"Received request for rainmap - grid_size: {grid_size}, density: {density}")
        result = generate_real_time_json(grid_size, density)
        logger.info(f"Successfully generated rainmap with {len(result['data'])} points")
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Error in /rainmap/realtime: {str(e)}")
        logger.error(traceback.format_exc())
        # Return empty but valid response instead of crashing
        return JSONResponse(
            status_code=200,  # Still return 200 but with error flag
            content={
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "original_points": 0,
                "interpolated_points": 0,
                "data": [],
                "error": f"Could not fetch data: {str(e)}"
            }
        )

# === 9. FastAPI MEXICAN CITIES Route ===
@router.get("/city")
async def get_mexican_cities(selectedCity: str = "Ciudad de Mexico"):
    """
    Returns precipitation data from specific cities
    """
    try:
        logger.info(f"Received request for city: {selectedCity}")
        
        # Find the city directly
        city = next((c for c in MEXICAN_CITIES if c["name"] == selectedCity), None)

        if not city:
            logger.warning(f"City not found: {selectedCity}")
            return JSONResponse(
                status_code=404, content={"error": f"City '{selectedCity}' not found"}
            )

        # Fetch precipitation
        data = fetch_point({"lat": city["lat"], "lon": city["lon"]})
        logger.info(f"City data fetched: {data}")
        
        return JSONResponse(content=data)

    except Exception as e:
        logger.error(f"Error in /rainmap/city: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={"error": "Internal Server Error", "detail": str(e)},
        )