from fastapi import APIRouter, Depends, HTTPException, Request, Query, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.core.database import get_db_secure as get_db
from app.core.events_security import get_current_events_user, require_role
from app.models.events.events_user import EventsUser
from app.models.events.secure_event import SecureEvent
from app.models.events.audit_log import EventAuditLog
from app.services.events.webhook_service import send_webhook

router = APIRouter(prefix="/logs", tags=["Logs & Audit"])


class AuditLogResponse(BaseModel):
    id: str
    action: str
    event_id: Optional[str]
    ticket_id: Optional[str]
    totem_id: Optional[str]
    actor_type: Optional[str]
    actor_id: Optional[str]
    ip_address: Optional[str]
    extra: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=List[AuditLogResponse])
async def list_logs(
    request: Request,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user),
    event_id: Optional[str] = None,
    action: Optional[str] = None,
    actor_type: Optional[str] = None,
    ticket_id: Optional[str] = None,
    totem_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = Query(100, le=500),
    offset: int = 0
):
    query = db.query(EventAuditLog)
    
    if event_id:
        query = query.filter(EventAuditLog.event_id == event_id)
    if action:
        query = query.filter(EventAuditLog.action.like(f"%{action}%"))
    if actor_type:
        query = query.filter(EventAuditLog.actor_type == actor_type)
    if ticket_id:
        query = query.filter(EventAuditLog.ticket_id == ticket_id)
    if totem_id:
        query = query.filter(EventAuditLog.totem_id == totem_id)
    
    if from_date:
        try:
            from_dt = datetime.fromisoformat(from_date)
            query = query.filter(EventAuditLog.created_at >= from_dt)
        except:
            pass
    
    if to_date:
        try:
            to_dt = datetime.fromisoformat(to_date)
            query = query.filter(EventAuditLog.created_at <= to_dt)
        except:
            pass
    
    return query.order_by(EventAuditLog.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/alerts", response_model=List[AuditLogResponse])
async def list_alerts(
    request: Request,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user),
    event_id: Optional[str] = None,
    limit: int = Query(50, le=200)
):
    alert_actions = [
        "checkin.not_found",
        "face.failed",
        "totem.offline",
        "qr.invalid",
        "security.login_failed"
    ]
    
    query = db.query(EventAuditLog).filter(
        EventAuditLog.action.in_(alert_actions)
    )
    
    if event_id:
        query = query.filter(EventAuditLog.event_id == event_id)
    
    return query.order_by(EventAuditLog.created_at.desc()).limit(limit).all()


@router.get("/by-action/{action}", response_model=List[AuditLogResponse])
async def get_logs_by_action(
    request: Request,
    action: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user),
    event_id: Optional[str] = None,
    limit: int = Query(100, le=500)
):
    query = db.query(EventAuditLog).filter(
        EventAuditLog.action.like(f"%{action}%")
    )
    
    if event_id:
        query = query.filter(EventAuditLog.event_id == event_id)
    
    return query.order_by(EventAuditLog.created_at.desc()).limit(limit).all()


@router.get("/by-ticket/{ticket_id}", response_model=List[AuditLogResponse])
async def get_logs_by_ticket(
    request: Request,
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user)
):
    logs = db.query(EventAuditLog).filter_by(ticket_id=ticket_id).order_by(
        EventAuditLog.created_at.desc()
    ).all()
    
    return logs


@router.get("/by-totem/{totem_id}", response_model=List[AuditLogResponse])
async def get_logs_by_totem(
    request: Request,
    totem_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user),
    limit: int = Query(100, le=500)
):
    logs = db.query(EventAuditLog).filter_by(totem_id=totem_id).order_by(
        EventAuditLog.created_at.desc()
    ).limit(limit).all()
    
    return logs


@router.get("/stats")
async def get_log_stats(
    request: Request,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user),
    event_id: Optional[str] = None,
    from_date: Optional[str] = None
):
    from sqlalchemy import func
    
    query = db.query(EventAuditLog)
    
    if event_id:
        query = query.filter(EventAuditLog.event_id == event_id)
    
    if from_date:
        try:
            from_dt = datetime.fromisoformat(from_date)
            query = query.filter(EventAuditLog.created_at >= from_dt)
        except:
            pass
    
    total = query.count()
    
    action_counts = query.with_entities(
        EventAuditLog.action,
        func.count(EventAuditLog.id)
    ).group_by(EventAuditLog.action).all()
    
    return {
        "total_logs": total,
        "by_action": {action: count for action, count in action_counts}
    }


@router.get("/export")
async def export_logs(
    request: Request,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(require_role("events_admin")),
    event_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    format: str = "json"
):
    query = db.query(EventAuditLog)
    
    if event_id:
        query = query.filter(EventAuditLog.event_id == event_id)
    
    if from_date:
        try:
            from_dt = datetime.fromisoformat(from_date)
            query = query.filter(EventAuditLog.created_at >= from_dt)
        except:
            pass
    
    if to_date:
        try:
            to_dt = datetime.fromisoformat(to_date)
            query = query.filter(EventAuditLog.created_at <= to_dt)
        except:
            pass
    
    logs = query.order_by(EventAuditLog.created_at.desc()).all()
    
    if format == "csv":
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "action", "event_id", "ticket_id", "totem_id", "actor_type", "actor_id", "ip_address", "created_at"])
        
        for log in logs:
            writer.writerow([
                log.id, log.action, log.event_id, log.ticket_id,
                log.totem_id, log.actor_type, log.actor_id,
                log.ip_address, log.created_at.isoformat() if log.created_at else ""
            ])
        
        return {
            "format": "csv",
            "filename": f"audit_logs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
            "data": output.getvalue()
        }
    
    return {
        "format": "json",
        "count": len(logs),
        "logs": [
            {
                "id": l.id,
                "action": l.action,
                "event_id": l.event_id,
                "ticket_id": l.ticket_id,
                "totem_id": l.totem_id,
                "actor_type": l.actor_type,
                "actor_id": l.actor_id,
                "ip_address": l.ip_address,
                "created_at": l.created_at.isoformat() if l.created_at else None
            }
            for l in logs
        ]
    }