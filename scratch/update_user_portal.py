import re

path = "platform/gateway/src/api/user_portal.py"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

# 1. Update list_user_payments
text = text.replace(
    '''@router.get("/payments", response_model=List[dict])
async def list_user_payments():
    """Fetch payment history transactions directly from MongoDB Atlas payments collection."""
    from common.database.mongodb import mongo_manager
    db = mongo_manager.get_database()
    if db is not None:
        try:
            cursor = db.payments.find({"user_id": "user_staff_01"}, {"_id": 0}).sort("_id", -1)''',
    '''@router.get("/payments", response_model=List[dict])
async def list_user_payments(request: Request):
    """Fetch payment history transactions directly from MongoDB Atlas payments collection."""
    from common.database.mongodb import mongo_manager
    db = mongo_manager.get_database()
    user_id = get_current_user_id(request)
    if db is not None:
        try:
            cursor = db.payments.find({"user_id": user_id}, {"_id": 0}).sort("_id", -1)'''
)

# 2. Update record_user_payment
text = text.replace(
    '''@router.post("/payments", status_code=status.HTTP_201_CREATED)
async def record_user_payment(req: PaymentCreateRequest):
    """Record a completed VNPAY payment transaction in MongoDB Atlas."""
    txn_id = f"VNP{secrets.randbelow(89999999) + 10000000}"
    payment_doc = {
        "txn_ref": txn_id,
        "amount": req.amount,
        "package": req.package,
        "user_id": "user_staff_01",''',
    '''@router.post("/payments", status_code=status.HTTP_201_CREATED)
async def record_user_payment(req: PaymentCreateRequest, request: Request):
    """Record a completed VNPAY payment transaction in MongoDB Atlas."""
    user_id = get_current_user_id(request)
    txn_id = f"VNP{secrets.randbelow(89999999) + 10000000}"
    payment_doc = {
        "txn_ref": txn_id,
        "amount": req.amount,
        "package": req.package,
        "user_id": user_id,'''
)

# 3. Update get_user_apis_state & update_user_apis_state
text = text.replace(
    '''@router.get("/apis-state")
@router.get("/apis")
async def get_user_apis_state():
    """Get active API states for user from MongoDB Atlas api_subscriptions collection."""
    enabled = await api_subscription_repository.get_user_subscriptions("user_staff_01")
    return {"enabled_apis": enabled}


@router.post("/apis-state")
@router.post("/apis")
async def update_user_apis_state(req: ApisStateUpdateRequest):
    """Update active API states for user in MongoDB Atlas api_subscriptions collection."""
    updated = await api_subscription_repository.update_user_subscriptions("user_staff_01", req.enabled_apis)
    return {"message": "API states updated successfully", "enabled_apis": updated}''',
    '''@router.get("/apis-state")
@router.get("/apis")
async def get_user_apis_state(request: Request):
    """Get active API states for user from MongoDB Atlas api_subscriptions collection."""
    user_id = get_current_user_id(request)
    enabled = await api_subscription_repository.get_user_subscriptions(user_id)
    return {"enabled_apis": enabled}


@router.post("/apis-state")
@router.post("/apis")
async def update_user_apis_state(req: ApisStateUpdateRequest, request: Request):
    """Update active API states for user in MongoDB Atlas api_subscriptions collection."""
    user_id = get_current_user_id(request)
    updated = await api_subscription_repository.update_user_subscriptions(user_id, req.enabled_apis)
    return {"message": "API states updated successfully", "enabled_apis": updated}'''
)

# 4. Update get_user_balance & recharge_user_balance
text = text.replace(
    '''@router.get("/balance")
async def get_user_balance():
    """Get paid balance from MongoDB Atlas api_subscriptions collection."""
    bal = await api_subscription_repository.get_user_paid_balance("user_staff_01")
    return {"paid_balance": bal}


@router.post("/recharge")
async def recharge_user_balance(req: RechargeBalanceRequest):
    """Recharge credits and record payment in MongoDB Atlas."""
    new_bal = await api_subscription_repository.recharge_user_balance(
        user_id="user_staff_01",
        add_credits=req.credits,
        amount=req.amount,
        package=req.package,
        project=req.project or "default"
    )
    return {"message": "Recharged successfully", "paid_balance": new_bal}''',
    '''@router.get("/balance")
async def get_user_balance(request: Request):
    """Get paid balance from MongoDB Atlas api_subscriptions collection."""
    user_id = get_current_user_id(request)
    bal = await api_subscription_repository.get_user_paid_balance(user_id)
    return {"paid_balance": bal}


@router.post("/recharge")
async def recharge_user_balance(req: RechargeBalanceRequest, request: Request):
    """Recharge credits and record payment in MongoDB Atlas."""
    user_id = get_current_user_id(request)
    new_bal = await api_subscription_repository.recharge_user_balance(
        user_id=user_id,
        add_credits=req.credits,
        amount=req.amount,
        package=req.package,
        project=req.project or "default"
    )
    return {"message": "Recharged successfully", "paid_balance": new_bal}'''
)

# Normalize newlines and write back
with open(path, "w", encoding="utf-8") as f:
    f.write(text.replace("\r\n", "\n"))
print("Updated user_portal.py successfully!")

