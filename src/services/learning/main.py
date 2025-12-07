from fastapi import FastAPI

app = FastAPI(title="TutorIA Learning Service")

@app.get("/")
def health_check():
    return {"status": "active", "service": "learning"}

@app.get("/health")
def health():
    return {"status": "ok"}