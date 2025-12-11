import os
import logging
from typing import List, Dict, Any
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from openai import AsyncOpenAI
# Ajuste de importación relativo para que funcione tanto en API como en Worker
try:
    from .client import VectorDBClient, VectorChunk
except ImportError:
    from client import VectorDBClient, VectorChunk

logger = logging.getLogger(__name__)

class QdrantService(VectorDBClient):
    def __init__(self):
        self.host = os.getenv("QDRANT_HOST", "qdrant")
        self.port = int(os.getenv("QDRANT_PORT", 6333))
        self.api_key = os.getenv("QDRANT_API_KEY", None)
        
        self.client = AsyncQdrantClient(host=self.host, port=self.port, api_key=self.api_key)
        self.openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.collection_name = "engineering_knowledge"

    async def ensure_collection(self):
        if await self.client.collection_exists(self.collection_name):
            return

        logger.info(f"Creando colección Qdrant: {self.collection_name}")
        await self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=models.VectorParams(
                size=1536,
                distance=models.Distance.COSINE
            )
        )

    async def _get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        clean_texts = [t.replace("\n", " ") for t in texts]
        response = await self.openai_client.embeddings.create(
            input=clean_texts,
            model="text-embedding-3-small"
        )
        return [data.embedding for data in response.data]

    async def upsert_chunks(self, chunks: List[VectorChunk]):
        if not chunks: return

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

        await self.client.upsert(collection_name=self.collection_name, points=points)
        logger.info(f"💾 Insertados {len(points)} vectores en Qdrant.")

    async def search(self, query: str, filters: Dict[str, Any], limit: int = 5) -> List[VectorChunk]:
        query_vector = (await self._get_embeddings_batch([query]))[0]
        
        must_filters = []
        for key, value in filters.items():
            must_filters.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))
            
        search_result = await self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            query_filter=models.Filter(must=must_filters) if must_filters else None,
            limit=limit
        )
        
        return [VectorChunk(id=str(hit.id), text=hit.payload.get("text", ""), metadata={k:v for k,v in hit.payload.items() if k!="text"}, score=hit.score) for hit in search_result]