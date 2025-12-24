from abc import ABC, abstractmethod
from src.services.learning.domain.entities import Exam

class ExamExporter(ABC):
    """
    Puerto (Interface) para la exportación de exámenes.
    Define el contrato que cualquier generador de PDF debe cumplir.
    """
    
    @abstractmethod
    async def export(self, exam: Exam) -> bytes:
        """
        Recibe una entidad Exam y devuelve los bytes del archivo generado.
        Es async porque la implementación podría requerir hilos o I/O.
        """
        pass