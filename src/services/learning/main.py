# src/services/learning/main.py
from fastapi import FastAPI

# Este servicio queda como "Microservicio Interno"
app = FastAPI(title="Learning Service Internal API")

@app.get("/")
def root():
    return {"status": "Learning Service (Internal) is Ready 🟢"}

@app.get("/health")
def health():
    return {"status": "healthy"}