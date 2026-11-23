
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, Payment
from app.schemas.user import AdminUserResponse, AdminCreditAllocation, AdminTransactionResponse
from app.core.auth import get_current_user

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@router.get("/users", response_model=list[AdminUserResponse])
async def get_all_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [AdminUserResponse.model_validate(u) for u in users]


@router.get("/transactions", response_model=list[AdminTransactionResponse])
async def get_all_transactions(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    payments = (
        db.query(Payment)
        .join(User, Payment.user_id == User.id)
        .order_by(Payment.created_at.desc())
        .all()
    )
    result = []
    for p in payments:
        result.append(AdminTransactionResponse(
            id=p.id,
            user_id=p.user_id,
            username=p.user.username,
            email=p.user.email,
            amount=p.amount,
            card_last4=p.card_last4,
            card_brand=p.card_brand,
            credits_added=p.credits_added,
            status=p.status,
            created_at=p.created_at,
        ))
    return result


@router.post("/allocate-credits")
async def allocate_credits(
    data: AdminCreditAllocation,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.credits = (user.credits or 0) + data.credits
    db.commit()

    return {
        "user_id": user.id,
        "username": user.username,
        "credits": user.credits,
    }


@router.get("/stats")
async def get_stats(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    total_users = db.query(User).count()
    paid_users = db.query(User).filter(User.has_paid == True).count()
    total_revenue = db.query(Payment).filter(Payment.status == "completed").count()
    from sqlalchemy import func
    revenue_sum = db.query(func.sum(Payment.amount)).filter(Payment.status == "completed").scalar() or 0

    return {
        "total_users": total_users,
        "paid_users": paid_users,
        "total_transactions": total_revenue,
        "total_revenue": round(float(revenue_sum), 2),
    }
