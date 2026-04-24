import asyncio
from datetime import datetime, timedelta
from app.core.database import SessionLocal
from app.core.config import settings
from app.models.events.secure_event import SecureEvent
from app.models.events.face_registration import FaceRegistration
from app.models.events.audit_log import EventAuditLog
from engines.base_engine import get_engine
import logging

logger = logging.getLogger(__name__)


async def auto_delete_expired_faces():
    if not settings.FACE_AUTO_DELETE:
        logger.info("Auto-delete is disabled")
        return
    
    logger.info("Starting face retention cleanup job...")
    
    db = SessionLocal()
    engine = get_engine()
    
    try:
        cutoff = datetime.utcnow() - timedelta(days=settings.FACE_RETENTION_DAYS)
        
        expired_events = db.query(SecureEvent).filter(
            SecureEvent.status == "ended",
            SecureEvent.ended_at < cutoff,
            SecureEvent.deleted_at == None
        ).all()
        
        logger.info(f"Found {len(expired_events)} expired events to process")
        
        for event in expired_events:
            try:
                await engine.delete_collection(event.namespace)
                logger.info(f"Deleted collection: {event.namespace}")
            except Exception as e:
                logger.error(f"Error deleting collection {event.namespace}: {e}")
            
            db.query(FaceRegistration).filter_by(
                event_id=event.id
            ).update({
                "status": "deleted",
                "deleted_at": datetime.utcnow()
            })
            
            event.deleted_at = datetime.utcnow()
            
            log = EventAuditLog(
                action="faces.auto_deleted",
                event_id=str(event.id),
                actor_type="system",
                extra={
                    "reason": "retention_policy",
                    "retention_days": settings.FACE_RETENTION_DAYS,
                    "ended_at": event.ended_at.isoformat() if event.ended_at else None
                }
            )
            db.add(log)
            db.commit()
            
            logger.info(f"Processed event {event.id} - faces deleted")
        
        logger.info(f"Face retention cleanup completed. Processed {len(expired_events)} events")
        
    except Exception as e:
        logger.error(f"Error in face retention job: {e}")
    finally:
        db.close()


async def get_retention_stats():
    db = SessionLocal()
    
    try:
        cutoff = datetime.utcnow() - timedelta(days=settings.FACE_RETENTION_DAYS)
        
        expired_count = db.query(SecureEvent).filter(
            SecureEvent.status == "ended",
            SecureEvent.ended_at < cutoff,
            SecureEvent.deleted_at == None
        ).count()
        
        faces_to_delete = db.query(FaceRegistration).join(SecureEvent).filter(
            SecureEvent.status == "ended",
            SecureEvent.ended_at < cutoff,
            FaceRegistration.status == "active"
        ).count()
        
        return {
            "expired_events": expired_count,
            "faces_to_delete": faces_to_delete,
            "retention_days": settings.FACE_RETENTION_DAYS,
            "auto_delete_enabled": settings.FACE_AUTO_DELETE
        }
        
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(auto_delete_expired_faces())