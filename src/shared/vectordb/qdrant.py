import os
import logging
from typing import List, Dict, Any, Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from openai import AsyncOpenAI

# --- IMPORTS DE DOMINIO ---
try:
    from src.services.learning.domain.entities import EngineeringBlock, SourceType
except ImportError:
    pass

# --- IMPORTS RELATIVOS ---
try:
    from .client import VectorDBClient, VectorChunk
except ImportError:
    class VectorChunk:
        def __init__(self, id, text, metadata=None, score=0.0):
            self.id = id
            self.text = text
            self.metadata = metadata or {}
            self.score = score
    class VectorDBClient:
        pass

logger = logging.getLogger(__name__)

class QdrantService(VectorDBClient):
    def __init__(self):
        # 1. Configuración de Conexión
        self.host = os.getenv("QDRANT_HOST", "tutor-ia-qdrant")
        self.port = int(os.getenv("QDRANT_PORT", 6333))
        self.api_key = os.getenv("QDRANT_API_KEY", None)
        self.collection_name = "engineering_knowledge"
        
        # Cliente Qdrant
        self.client = AsyncQdrantClient(host=self.host, port=self.port, api_key=self.api_key)
        
        # Cliente OpenAI (para generar vectores)
        self.openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.embedding_model = "text-embedding-3-small"

    async def ensure_collection(self):
        """Crea la colección si no existe (Vital para inicio frío)"""
        if await self.client.collection_exists(self.collection_name):
            return

        logger.info(f"🆕 Creando colección Qdrant: {self.collection_name}")
        await self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=models.VectorParams(
                size=1536,
                distance=models.Distance.COSINE
            )
        )

    async def _get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Genera vectores usando OpenAI"""
        clean_texts = [t.replace("\n", " ") for t in texts]
        response = await self.openai_client.embeddings.create(
            input=clean_texts,
            model=self.embedding_model
        )
        return [data.embedding for data in response.data]

    async def upsert_chunks(self, chunks: List[VectorChunk]):
        """Guarda chunks en la DB. Usado por el Processor (Ingesta)."""
        if not chunks:
            return

        texts = [chunk.text for chunk in chunks]
        try:
            vectors = await self._get_embeddings_batch(texts)
        except Exception as e:
            logger.error(f"Error generando embeddings: {e}")
            raise e

        points = []
        for i, chunk in enumerate(chunks):
            points.append(models.PointStruct(
                id=chunk.id,
                vector=vectors[i],
                payload={"text": chunk.text, **chunk.metadata}
            ))

        await self.ensure_collection()
        await self.client.upsert(collection_name=self.collection_name, points=points)
        logger.info(f"💾 Insertados {len(points)} vectores en Qdrant.")

    async def search(self, query: str, filters: Dict[str, Any] = None, limit: int = 5) -> List[EngineeringBlock]:
        """
        Busca contexto relevante.
        CAMBIO CLAVE: Devuelve 'EngineeringBlock' para que ContentSelector funcione.
        """
        # 1. Vectorizar la query
        query_vectors = await self._get_embeddings_batch([query])
        query_vector = query_vectors[0]
        
        # 2. Construir Filtros
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

        # 3. Buscar (Con manejo de errores seguro)
        try:
            hits = await self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=qdrant_filter,
                limit=limit
            )
        except Exception as e:
            if "Not found: Collection" in str(e):
                logger.warning(f"⚠️ Colección '{self.collection_name}' no encontrada. Devolviendo vacío.")
                return []
            logger.error(f"Error buscando en Qdrant: {e}")
            raise e

        # 4. Mapeo a Objetos de Dominio (Adapter Pattern)
        results = []
        for hit in hits:
            payload = hit.payload or {}
            
            # ========== CONVERSIÓN SEGURA DE STRING A ENUM ==========
            source_type_str = payload.get("source_type", "theory_slides")
            source_type = SourceType.THEORY_SLIDES  # Default seguro
            
            # Intentamos convertir el string a Enum
            try:
                for st in SourceType:
                    if st.value == source_type_str:
                        source_type = st
                        break
            except Exception as e:
                logger.debug(f"⚠️ source_type '{source_type_str}' no reconocido, usando default: {e}")
            
            # Construimos el bloque con seguridad
            block = EngineeringBlock(
                id=str(hit.id),
                course_id=payload.get("course_id", filters.get("course_id", "unknown") if filters else "unknown"),
                source_type=source_type,  # ✅ Ya es Enum convertido de forma segura
                
                # Qdrant guarda el texto en 'text', pero EngineeringBlock usa 'clean_text'
                clean_text=payload.get("text", ""), 
                
                # Recuperamos los campos ricos si existen
                latex_content=payload.get("latex_content"),
                topics=payload.get("topics", []),
                is_problem=payload.get("is_problem", False),
                complexity=payload.get("complexity", 0.5)
            )
            results.append(block)

        return results