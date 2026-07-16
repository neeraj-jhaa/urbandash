"""
UrbanDash complaint triage API.
"""
import logging
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlalchemy.orm import Session

from . import models, schemas
from .database import Base, engine, get_db
from .classify import classify_message, ClassificationError
from .seed_data import run_seed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("urbandash")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="UrbanDash Complaint Triage API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def seed_on_startup():
    db = next(get_db())
    try:
        run_seed(db)
    except Exception:  # noqa: BLE001
        logger.exception("Seeding failed (this is non-fatal, continuing).")
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/complaints/ingest", response_model=schemas.ComplaintOut, status_code=201)
def ingest_complaint(payload: schemas.ComplaintIngest, db: Session = Depends(get_db)):
    complaint = models.Complaint(
        channel=payload.channel,
        customer_identifier=payload.customer_identifier.strip(),
        complainant_type=payload.complainant_type,
        raw_message=payload.raw_message.strip(),
        status=models.ComplaintStatus.open,
    )
    db.add(complaint)
    db.commit()
    db.refresh(complaint)
    return complaint


@app.post("/complaints/{complaint_id}/classify", response_model=schemas.ComplaintOut)
def classify_complaint(complaint_id: str, db: Session = Depends(get_db)):
    complaint = db.get(models.Complaint, complaint_id)
    if complaint is None:
        raise HTTPException(status_code=404, detail=f"Complaint '{complaint_id}' not found.")

    if not complaint.raw_message or not complaint.raw_message.strip():
        raise HTTPException(
            status_code=422, detail="Complaint has no message text to classify."
        )

    try:
        issues = classify_message(
            raw_message=complaint.raw_message,
            complainant_type=complaint.complainant_type.value
            if hasattr(complaint.complainant_type, "value")
            else complaint.complainant_type,
            channel=complaint.channel.value
            if hasattr(complaint.channel, "value")
            else complaint.channel,
        )
    except ClassificationError as exc:
        logger.error("Classification failed for %s: %s", complaint_id, exc)
        raise HTTPException(status_code=502, detail=f"Classification failed: {exc}") from exc

    # Replace any prior classifications for this complaint (re-classify).
    for existing in list(complaint.classifications):
        db.delete(existing)
    db.flush()

    for idx, issue in enumerate(issues):
        db.add(
            models.Classification(
                complaint_id=complaint.id,
                sub_index=idx,
                category=issue["category"],
                urgency=issue["urgency"],
                routed_team=issue["routed_team"],
                reasoning=issue["reasoning"],
                is_noise=issue["is_noise"],
                overridden=False,
            )
        )

    db.commit()
    db.refresh(complaint)
    return complaint


@app.get("/queue", response_model=list[schemas.QueueItem])
def get_queue(
    team: Optional[str] = Query(default=None),
    urgency: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    include_noise: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    q = (
        db.query(models.Classification, models.Complaint)
        .join(models.Complaint, models.Classification.complaint_id == models.Complaint.id)
    )

    if not include_noise:
        q = q.filter(models.Classification.is_noise.is_(False))
    if team:
        q = q.filter(models.Classification.routed_team == team)
    if urgency:
        if urgency not in schemas.VALID_URGENCY:
            raise HTTPException(status_code=422, detail=f"Invalid urgency '{urgency}'.")
        q = q.filter(models.Classification.urgency == urgency)
    if status:
        if status not in schemas.VALID_STATUSES:
            raise HTTPException(status_code=422, detail=f"Invalid status '{status}'.")
        q = q.filter(models.Complaint.status == status)

    q = q.order_by(models.Complaint.created_at.desc(), models.Classification.sub_index.asc())

    results = []
    for classification, complaint in q.all():
        results.append(
            schemas.QueueItem(
                classification_id=classification.id,
                complaint_id=complaint.id,
                sub_index=classification.sub_index,
                category=classification.category,
                urgency=classification.urgency.value
                if hasattr(classification.urgency, "value")
                else classification.urgency,
                routed_team=classification.routed_team,
                reasoning=classification.reasoning,
                is_noise=classification.is_noise,
                overridden=classification.overridden,
                channel=complaint.channel.value
                if hasattr(complaint.channel, "value")
                else complaint.channel,
                customer_identifier=complaint.customer_identifier,
                complainant_type=complaint.complainant_type.value
                if hasattr(complaint.complainant_type, "value")
                else complaint.complainant_type,
                raw_message=complaint.raw_message,
                status=complaint.status.value
                if hasattr(complaint.status, "value")
                else complaint.status,
                created_at=complaint.created_at,
            )
        )
    return results


@app.get("/complaints/{complaint_id}", response_model=schemas.ComplaintOut)
def get_complaint(complaint_id: str, db: Session = Depends(get_db)):
    complaint = db.get(models.Complaint, complaint_id)
    if complaint is None:
        raise HTTPException(status_code=404, detail=f"Complaint '{complaint_id}' not found.")
    return complaint


@app.patch("/complaints/{complaint_id}/status", response_model=schemas.ComplaintOut)
def update_status(
    complaint_id: str, payload: schemas.StatusUpdate, db: Session = Depends(get_db)
):
    complaint = db.get(models.Complaint, complaint_id)
    if complaint is None:
        raise HTTPException(status_code=404, detail=f"Complaint '{complaint_id}' not found.")
    complaint.status = payload.status
    db.commit()
    db.refresh(complaint)
    return complaint


@app.patch("/classifications/{classification_id}", response_model=schemas.ClassificationOut)
def override_classification(
    classification_id: str,
    payload: schemas.ClassificationOverride,
    db: Session = Depends(get_db),
):
    classification = db.get(models.Classification, classification_id)
    if classification is None:
        raise HTTPException(
            status_code=404, detail=f"Classification '{classification_id}' not found."
        )

    changed = False
    if payload.category is not None:
        classification.category = payload.category
        changed = True
    if payload.urgency is not None:
        classification.urgency = payload.urgency
        changed = True
    if payload.routed_team is not None:
        classification.routed_team = payload.routed_team
        changed = True
    if payload.reasoning is not None:
        classification.reasoning = payload.reasoning
        changed = True
    if payload.is_noise is not None:
        classification.is_noise = payload.is_noise
        if payload.is_noise:
            classification.routed_team = "none"
        changed = True

    if changed:
        classification.overridden = True
        db.commit()
        db.refresh(classification)

    return classification


@app.get("/complaints", response_model=list[schemas.ComplaintOut])
def list_complaints(db: Session = Depends(get_db)):
    return db.query(models.Complaint).order_by(models.Complaint.created_at.desc()).all()


@app.exception_handler(ValidationError)
def validation_exception_handler(request, exc):
    raise HTTPException(status_code=422, detail=str(exc))
