# app.py (root of repo)

import uvicorn
from src.main import app  # this imports the FastAPI instance from app/main.py

if __name__ == "__main__":
    # S2I Python image will run: python app.py
    uvicorn.run(app, host="0.0.0.0", port=8080)
