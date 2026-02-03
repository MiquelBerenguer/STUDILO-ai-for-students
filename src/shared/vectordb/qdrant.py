import os
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

# Usamos las versiones asíncronas para alto rendimiento
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# --- DTOs (Data Transfer Objects) ---
# Definimos estos objetos AQUÍ para no depender de otros módulos
@dataclass
class VectorChunk:
    """Objeto de entrada: Lo que quieres guardar"""
    id: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class SearchResult:
    """Objeto de salida: Lo que Qdrant devuelve"""
    id: str
    text: str
    score: float
    metadata: Dict[str, Any]

class QdrantService:
    def __init__(self):
        # 1. Configuración desde variables de entorno
        self.host = os.getenv("QDRANT_HOST", "localhost") # Default localhost para dev local
        self.port = int(os.getenv("QDRANT_PORT", 6333))
        self.api_key = os.getenv("QDRANT_API_KEY", None) # Solo necesario en Cloud/Prod
        self.collection_name = "engineering_knowledge"
        
        # 2. Clientes Asíncronos
        self.client = AsyncQdrantClient(host=self.host, port=self.port, api_key=self.api_key)
        
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            logger.warning("⚠️ OPENAI_API_KEY no encontrada. La vectorización fallará.")
        
        self.openai_client = AsyncOpenAI(api_key=openai_key)
        self.embedding_model = "text-embedding-3-small"
        self.vector_size = 1536

    async def ensure_collection(self):
        """Crea la colección si no existe (Idempotente)"""
        try:
            if await self.client.collection_exists(self.collection_name):
                return

            logger.info(f"🆕 Creando colección Qdrant: {self.collection_name}")
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.vector_size,
                    distance=models.Distance.COSINE
                )
            )
        except Exception as e:
            logger.error(f"Error verificando colección Qdrant: {e}")
            # No lanzamos error aquí para permitir reintentos, pero logueamos fuerte

    async def _get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Genera vectores usando OpenAI"""
        # Limpieza básica para mejorar calidad de embeddings
        clean_texts = [t.replace("\n", " ") for t in texts]
        try:
            response = await self.openai_client.embeddings.create(
                input=clean_texts,
                model=self.embedding_model
            )
            # Ordenamos por índice para asegurar correspondencia
            return [data.embedding for data in response.data]
        except Exception as e:
            logger.error(f"❌ Error conectando con OpenAI: {e}")
            raise e

    async def upsert_chunks(self, chunks: List[VectorChunk]):
        """
        Guarda chunks en la DB.
        Recibe una lista de objetos VectorChunk.
        """
        if not chunks:
            return

        texts = [chunk.text for chunk in chunks]
        
        # 1. Generar Embeddings
        vectors = await self._get_embeddings_batch(texts)

        # 2. Preparar Puntos Qdrant
        points = []
        for i, chunk in enumerate(chunks):
            # Guardamos el texto en el payload para poder recuperarlo (RAG)
            payload = chunk.metadata.copy()
            payload["text_content"] = chunk.text 

            points.append(models.PointStruct(
                id=chunk.id,
                vector=vectors[i],
                payload=payload
            ))

        # 3. Subir
        await self.ensure_collection()
        await self.client.upsert(
            collection_name=self.collection_name, 
            points=points,
            wait=True # Esperamos confirmación
        )
        logger.info(f"💾 Insertados {len(points)} vectores en Qdrant.")

    async def search(self, query: str, filters: Dict[str, Any] = None, limit: int = 5) -> List[SearchResult]:
        """
        Busca contexto relevante.
        Devuelve objetos genéricos SearchResult.
        """
        # 1. Vectorizar la query
        query_vectors = await self._get_embeddings_batch([query])
        query_vector = query_vectors[0]
        
        # 2. Construir Filtros de Qdrant
        qdrant_filter = None
        if filters:
            must_conditions = []
            for key, value in filters.items():
                must_conditions.append(models.FieldCondition(
                    key=key, 
                    match=models.MatchValue(value=value)
                ))
            if must_conditions:
                qdrant_filter = models.Filter(must=must_conditions)

        # 3. Buscar
        hits = await self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            query_filter=qdrant_filter,
            limit=limit,
            with_payload=True
        )

        # 4. Mapeo a DTO Genérico (Desacoplado del dominio)
        results = []
        for hit in hits:
            payload = hit.payload or {}
            text = payload.get("text_content", "") # Recuperamos el texto guardado
            
            # Limpiamos el payload para no duplicar el texto en metadata
            meta = {k: v for k, v in payload.items() if k != "text_content"}
            
            results.append(SearchResult(
                id=str(hit.id),
                text=text,
                score=hit.score,
                metadata=meta
            ))

        return results