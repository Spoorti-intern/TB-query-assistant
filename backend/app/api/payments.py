
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, Payment
from app.schemas.user import PaymentRequest, PaymentResponse, UserResponse
from app.core.auth import get_current_user

router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.post("/process", response_model=PaymentResponse)
async def process_payment(
    data: PaymentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Accept any card details (dummy/showcase mode)
    card_clean = data.card_number.replace(" ", "").replace("-", "")

    # Determine card brand
    card_brand = "Visa"
    if card_clean.startswith("5"):
        card_brand = "Mastercard"
    elif card_clean.startswith("3"):
        card_brand = "Amex"
    elif card_clean.startswith("6"):
        card_brand = "Discover"

    card_last4 = card_clean[-4:]
    credits_to_add = 50

    # Create payment record
    payment = Payment(
        user_id=current_user.id,
        amount=data.amount,
        card_last4=card_last4,
        card_brand=card_brand,
        credits_added=credits_to_add,
        status="completed",
    )
    db.add(payment)

    # Update user credits
    current_user.credits = (current_user.credits or 0) + credits_to_add
    current_user.has_paid = True
    db.commit()
    db.refresh(payment)

    return PaymentResponse.model_validate(payment)


@router.get("/history", response_model=list[PaymentResponse])
async def get_payment_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payments = (
        db.query(Payment)
        .filter(Payment.user_id == current_user.id)
        .order_by(Payment.created_at.desc())
        .all()
    )
    return [PaymentResponse.model_validate(p) for p in payments]


@router.get("/credits")
async def get_credits(current_user: User = Depends(get_current_user)):
    return {
        "credits": current_user.credits,
        "has_paid": current_user.has_paid,
    }


@router.post("/use-credit")
async def use_credit(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.credits <= 0:
        raise HTTPException(status_code=402, detail="No credits remaining")

    current_user.credits = current_user.credits - 1
    db.commit()

    return {
        "credits": current_user.credits,
        "has_paid": current_user.has_paid,
    }
