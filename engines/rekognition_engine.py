import boto3
import base64
import io
from typing import Optional
from PIL import Image
import cv2
import numpy as np
from engines.base_engine import BaseFaceEngine, FaceMatch, FaceQualityResult
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


class RekognitionEngine(BaseFaceEngine):

    def __init__(self):
        self.client = boto3.client(
            "rekognition",
            region_name=settings.AWS_REKOGNITION_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )
        self.s3_client = boto3.client(
            "s3",
            region_name=settings.AWS_REKOGNITION_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )

    async def create_collection(self, namespace: str) -> None:
        try:
            self.client.create_collection(CollectionId=namespace)
            logger.info(f"Collection created: {namespace}")
        except self.client.exceptions.ResourceAlreadyExistsException:
            logger.info(f"Collection already exists: {namespace}")
        except Exception as e:
            logger.error(f"Error creating collection {namespace}: {e}")
            raise

    async def index_face(
        self, namespace: str, image_base64: str, ticket_id: str
    ) -> str:
        image_bytes = base64.b64decode(image_base64)
        
        try:
            response = self.client.index_faces(
                CollectionId=namespace,
                Image={"Bytes": image_bytes},
                ExternalImageId=ticket_id,
                MaxFaces=1,
                QualityFilter="MEDIUM"
            )
            
            if not response["FaceRecords"]:
                raise ValueError("No face detected in image")
            
            face_id = response["FaceRecords"][0]["Face"]["FaceId"]
            logger.info(f"Face indexed: {face_id} for ticket {ticket_id}")
            return face_id
            
        except self.client.exceptions.InvalidParameterException as e:
            logger.error(f"Invalid parameter for indexing: {e}")
            raise ValueError("Invalid image or face detection failed")

    async def search_face(
        self, namespace: str, image_base64: str
    ) -> Optional[FaceMatch]:
        image_bytes = base64.b64decode(image_base64)
        
        try:
            response = self.client.search_faces_by_image(
                CollectionId=namespace,
                Image={"Bytes": image_bytes},
                MaxFaces=1,
                FaceMatchThreshold=settings.FACE_SIMILARITY_THRESHOLD * 100
            )
            
            if not response["FaceMatches"]:
                return None
            
            match = response["FaceMatches"][0]
            return FaceMatch(
                external_face_id=match["Face"]["FaceId"],
                ticket_id=match["Face"]["ExternalImageId"],
                confidence=match["Similarity"] / 100
            )
            
        except self.client.exceptions.InvalidParameterException:
            return None
        except Exception as e:
            logger.error(f"Error searching face: {e}")
            return None

    async def delete_face(
        self, namespace: str, external_face_id: str
    ) -> None:
        try:
            self.client.delete_faces(
                CollectionId=namespace,
                FaceIds=[external_face_id]
            )
            logger.info(f"Face deleted: {external_face_id}")
        except Exception as e:
            logger.error(f"Error deleting face {external_face_id}: {e}")

    async def delete_collection(self, namespace: str) -> None:
        try:
            self.client.delete_collection(CollectionId=namespace)
            logger.info(f"Collection deleted: {namespace}")
        except self.client.exceptions.ResourceNotFoundException:
            logger.info(f"Collection not found: {namespace}")
        except Exception as e:
            logger.error(f"Error deleting collection {namespace}: {e}")

    async def check_image_quality(
        self, image_base64: str
    ) -> FaceQualityResult:
        image_bytes = base64.b64decode(image_base64)
        
        try:
            response = self.client.detect_faces(
                Image={"Bytes": image_bytes},
                Attributes=["QUALITY"]
            )
            
            if not response["FaceDetails"]:
                return FaceQualityResult(
                    quality_score=0.0,
                    has_face=False,
                    issues=["No face detected"]
                )
            
            face = response["FaceDetails"][0]
            quality = face.get("Quality", {})
            brightness = quality.get("Brightness", 0)
            sharpness = quality.get("Sharpness", 0)
            
            quality_score = (brightness + sharpness) / 200
            
            issues = []
            if brightness < 40:
                issues.append("Image too dark")
            if brightness > 90:
                issues.append("Image too bright")
            if sharpness < 60:
                issues.append("Image not sharp enough")
            
            return FaceQualityResult(
                quality_score=quality_score,
                has_face=True,
                issues=issues
            )
            
        except Exception as e:
            logger.error(f"Error checking image quality: {e}")
            return FaceQualityResult(
                quality_score=0.0,
                has_face=False,
                issues=[str(e)]
            )

    async def list_faces(self, namespace: str) -> list:
        try:
            response = self.client.list_faces(CollectionId=namespace)
            return response.get("Faces", [])
        except Exception as e:
            logger.error(f"Error listing faces in {namespace}: {e}")
            return []