#Create FASTAPI app
#Load Settings
#Connect to MongoDB on startup
#Expose at least a health route to test everything wires correctly
#In future include candidate/search/feedback routes and middlewares.

from fastapi import FastAPI
from app.config.settings import Settings
from app.db.client import connect_to_mongo , close_mongo_connection
from fastapi.responses import JSONResponse
import uvicorn

# function create_app(): settings = Settings()  # from app.config.settings
def create_app() -> FastAPI:
    settings = Settings()  # from app.config.settings
    app = FastAPI(title="Candidate Recommendation API")

    @app.on_event("startup")
    async def startup_event():
        # Ensure MongoDB connection is established
        connect_to_mongo(settings)
        # we have to validate indexes here

    @app.on_event("shutdown")
    async def shutdown_event():
        # Close MongoDB connection
        close_mongo_connection()

    @app.get("/health", response_class=JSONResponse)
    async def health_check():
        return {"status": "ok"}
    # include candidate/search/feedback routes 

    return app
