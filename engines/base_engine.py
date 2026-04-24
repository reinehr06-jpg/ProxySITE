from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class FaceMatch:
    external_face_id: str
    ticket_id: str
    confidence: float


class FaceQualityResult:
    def __init__(self, quality_score: float, has_face: bool = True, issues: list = None):
        self.quality_score = quality_score
        self.has_face = has_face
        self.issues = issues or []


class BaseFaceEngine(ABC):

    @abstractmethod
    async def create_collection(self, namespace: str) -> None:
        pass

    @abstractmethod
    async def index_face(
        self, namespace: str, image_base64: str, ticket_id: str
    ) -> str:
        pass

    @abstractmethod
    async def search_face(
        self, namespace: str, image_base64: str
    ) -> Optional[FaceMatch]:
        pass

    @abstractmethod
    async def delete_face(
        self, namespace: str, external_face_id: str
    ) -> None:
        pass

    @abstractmethod
    async def delete_collection(self, namespace: str) -> None:
        pass

    @abstractmethod
    async def check_image_quality(
        self, image_base64: str
    ) -> FaceQualityResult:
        pass


def get_engine() -> BaseFaceEngine:
    from app.core.config import settings
    if settings.FACE_ENGINE == "aws_rekognition":
        from engines.rekognition_engine import RekognitionEngine
        return RekognitionEngine()
    elif settings.FACE_ENGINE == "compreface":
        from engines.compreface_engine import ComprefaceEngine
        return ComprefaceEngine()
    else:
        from engines.rekognition_engine import RekognitionEngine
        return RekognitionEngine()