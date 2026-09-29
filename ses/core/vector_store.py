import logging
from collections import OrderedDict
from typing import Iterable, List, Optional, Union

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from ses.config import QDRANT_URL, QDRANT_API_KEY, VECTOR_SIZE

logger = logging.getLogger(__name__)


class QdrantVectorStore:
    def __init__(self, url: Optional[str] = None, api_key: Optional[str] = None, max_cache_size: int = 1000) -> None:
        self._url = url or QDRANT_URL
        self._api_key = api_key or QDRANT_API_KEY

        self.client = AsyncQdrantClient(url=self._url, api_key=self._api_key)
        self._collections_cache = OrderedDict()
        self._max_cache_size = max_cache_size

    def _add_to_cache(self, collection_name: str) -> None:
        self._collections_cache[collection_name] = True
        self._collections_cache.move_to_end(collection_name)
        if len(self._collections_cache) > self._max_cache_size:
            self._collections_cache.popitem(last=False)

    async def ensure_collection(self, collection_name: str) -> None:
        if collection_name in self._collections_cache:
            self._collections_cache.move_to_end(collection_name)
            return

        exists = False
        try:
            await self.client.get_collection(collection_name)
            exists = True
            self._add_to_cache(collection_name)
        except Exception:
            exists = False

        if not exists:
            try:
                await self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=qmodels.VectorParams(
                        size=VECTOR_SIZE,
                        distance=qmodels.Distance.COSINE,
                    ),
                )
                self._add_to_cache(collection_name)
            except Exception as exc:
                error_str = str(exc).lower()
                if "already exists" in error_str or "conflict" in error_str:
                    self._add_to_cache(collection_name)
                    logger.info("Collection %s already exists (race condition handled)", collection_name)
                else:
                    logger.error("Error creating collection: %s", exc, exc_info=True)

    async def upsert_points(self, collection_name: str, points: Union[List[qmodels.PointStruct], qmodels.Batch]) -> None:
        # If it's already a Batch or a list, pass it directly.
        # If it's a generator/iterable (and not Batch/list), convert to list.
        if not isinstance(points, (list, qmodels.Batch)):
            points = list(points)

        await self.client.upsert(collection_name=collection_name, points=points)

    async def search(
        self,
        collection_name: str,
        query_vector: List[float],
        limit: int,
        score_threshold: float,
        with_payload: qmodels.PayloadSelectorExclude,
        with_vectors: bool,
    ):
        res = await self.client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=with_payload,
            with_vectors=with_vectors,
        )
        return res.points

    async def search_batch(self, collection_name: str, requests: List[qmodels.QueryRequest]):
        res = await self.client.query_batch_points(collection_name=collection_name, requests=requests)
        return [r.points for r in res]

    async def retrieve(self, collection_name: str, ids: List[str], with_payload: bool):
        return await self.client.retrieve(
            collection_name=collection_name,
            ids=ids,
            with_payload=with_payload,
        )

    async def delete(self, collection_name: str, points: qmodels.PointIdsList) -> None:
        await self.client.delete(collection_name=collection_name, points_selector=points)

    async def delete_by_payload(self, collection_name: str, key: str, value: str) -> None:
        await self.client.delete(
            collection_name=collection_name,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key=key,
                            match=qmodels.MatchValue(value=value),
                        )
                    ]
                )
            ),
        )

    async def delete_collection(self, collection_name: str) -> None:
        await self.client.delete_collection(collection_name)
        if collection_name in self._collections_cache:
            del self._collections_cache[collection_name]

    async def get_collection(self, collection_name: str):
        return await self.client.get_collection(collection_name)

    async def clear_cache(self) -> None:
        self._collections_cache.clear()
