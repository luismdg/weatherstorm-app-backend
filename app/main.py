from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import storm_routes, rainmap_routes
import os


app = FastAPI(title="Meteorological Backend")

# Allow CORS so frontend (localhost:3000) can access backend (localhost:8000)

app.add_middleware(
    CORSMiddleware,
    # allow_origins=["http://localhost:3000"],  # React dev server
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(storm_routes.router, prefix="/api", tags=["Storm"])
app.include_router(rainmap_routes.router, prefix="/rainmap", tags=["Rainmap"])


@app.get("/")
async def root():
    return {"message": "Backend running successfully"}


# Railway necesita esto
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
