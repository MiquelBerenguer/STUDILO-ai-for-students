from fastapi import APIRouter, HTTPException, status, Depends
from typing import Annotated

# 1. Importamos Seguridad (Igual que en documents.py)
from app.dependencies import get_current_user
# Si tienes un modelo de usuario tipado, úsalo, si no, usamos el genérico
# from src.shared.database.models import User 

# 2. Importamos el Cerebro Nuevo
from src.services.solver.schemas import SolverRequest, SolverResponse
from src.services.solver.service import SolverService
from src.shared.vectordb.qdrant import QdrantService
from src.services.ai.service import AIService

router = APIRouter(
    prefix="/solver",
    tags=["Solver (TutorIA V2)"]
)

# --- FACTORÍA DE SERVICIOS ---
# Esto monta las piezas solo cuando se necesita
def get_solver_service():
    qdrant = QdrantService()
    ai = AIService()
    return SolverService(qdrant_service=qdrant, ai_service=ai)

@router.post("/ask", response_model=SolverResponse)
async def ask_tutor_v2(
    request_body: SolverRequest,
    current_user = Depends(get_current_user), # 🔒 PROTEGIDO CON JWT
    service: SolverService = Depends(get_solver_service)
):
    """
    Nuevo endpoint de resolución de dudas (Motor V2).
    - Usa RAG (Apuntes) + CoT (Razonamiento).
    - Devuelve JSON estructurado con LaTeX y Ejemplos.
    """
    try:
        # SOBRESCRIBIMOS el user_id del request con el del Token real (Seguridad)
        # Asumimos que request_body.user_id venía del frontend, pero mandamos el real
        real_user_id = str(current_user.id)
        
        # Inyectamos el ID real en la petición para filtrar los apuntes correctos
        # (Nota: SolverRequest es un Pydantic model, podemos modificarlo o pasarlo)
        request_body.user_id = real_user_id

        response = await service.solve_doubt(request_body)
        return response

    except Exception as e:
        print(f"❌ ERROR SOLVER V2: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"TutorIA tuvo un problema interno: {str(e)}"
        )