from typing import Optional
import httpx
import base64
import json
from engines.base_engine import BaseFaceEngine, FaceMatch, FaceQualityResult
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


class CompreFaceEngine(BaseFaceEngine):

    def __init__(self):
        self.base_url = settings.COMPREFACE_URL
        self.api_key = settings.COMPREFACE_API_KEY
        self.headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }

    async def create_collection(self, namespace: str) -> None:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/facesets",
                    headers=self.headers,
                    json={"name": namespace},
                    timeout=10.0
                )
                if response.status_code == 200:
                    logger.info(f"Collection created: {namespace}")
                elif response.status_code == 409:
                    logger.info(f"Collection already exists: {namespace}")
                else:
                    logger.warning(f"Create collection response: {response.status_code}")
        except Exception as e:
            logger.error(f"Error creating collection {namespace}: {e}")

    async def index_face(
        self, namespace: str, image_base64: str, ticket_id: str
    ) -> str:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/faces",
                    headers=self.headers,
                    json={
                        "image": image_base64,
                        "subject": ticket_id,
                        "faceset_name": namespace
                    },
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    raise ValueError(f"Failed to index face: {response.text}")
                
                result = response.json()
                if not result.get("result"):
                    raise ValueError("No face detected in image")
                
                face_id = result.get("face_id")
                return face_id
                
        except httpx.TimeoutException:
            raise ValueError("Timeout while indexing face")
        except Exception as e:
            logger.error(f"Error indexing face: {e}")
            raise ValueError(f"Face indexing failed: {str(e)}")

    async def search_face(
        self, namespace: str, image_base64: str
    ) -> Optional[FaceMatch]:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/recognize",
                    headers=self.headers,
                    json={
                        "image": image_base64,
                        "faceset_name": namespace
                    },
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    return None
                
                result = response.json()
                if not result.get("result"):
                    return None
                
                faces = result.get("faces", [])
                if not faces:
                    return None
                
                best_match = faces[0]
                return FaceMatch(
                    external_face_id=best_match.get("face_id", ""),
                    ticket_id=best_match.get("subject", ""),
                    confidence=best_match.get("similarity", 0) / 100
                )
                
        except Exception as e:
            logger.error(f"Error searching face: {e}")
            return None

    async def delete_face(
        self, namespace: str, external_face_id: str
    ) -> None:
        try:
            async with httpx.AsyncClient() as client:
                await client.delete(
                    f"{self.base_url}/api/v1/faces/{external_face_id}",
                    headers=self.headers,
                    params={"faceset_name": namespace},
                    timeout=10.0
                )
                logger.info(f"Face deleted: {external_face_id}")
        except Exception as e:
            logger.error(f"Error deleting face {external_face_id}: {e}")

    async def delete_collection(self, namespace: str) -> None:
        try:
            async with httpx.AsyncClient() as client:
                await client.delete(
                    f"{self.base_url}/api/v1/facesets/{namespace}",
                    headers=self.headers,
                    timeout=10.0
                )
                logger.info(f"Collection deleted: {namespace}")
        except Exception as e:
            logger.error(f"Error deleting collection {namespace}: {e}")

    async def check_image_quality(
        self, image_base64: str
    ) -> FaceQualityResult:
        return FaceQualityResult(
            quality_score=0.8,
            has_face=True,
            issues=[]
        )