from abc import ABC, abstractmethod
from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class VectorChunk:
    id: str
    text: str
    metadata: Dict[str, Any]
    score: float = 0.0

class VectorDBClient(ABC):
    """Interfaz abstracta para el motor de búsqueda vectorial (Pinecone, Qdrant, etc)."""
    
    @abstractmethod
    async def search(
        self, 
        query: str, 
        filters: Dict[str, Any], 
        limit: int = 3
    ) -> List[VectorChunk]:
        pass