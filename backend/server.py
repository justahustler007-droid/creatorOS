from fastapi import FastAPI, APIRouter, HTTPException, Response, Request, Depends
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
import httpx

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== MODELS ====================

class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    early_access: bool = False
    onboarding_complete: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CreatorProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    creator_name: str
    bio: Optional[str] = None
    youtube_link: Optional[str] = None
    instagram_handle: Optional[str] = None
    follower_count: int = 0
    niche: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None
    detected_platform: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CreatorProfileCreate(BaseModel):
    creator_name: str
    bio: Optional[str] = None
    youtube_link: Optional[str] = None
    instagram_handle: Optional[str] = None
    follower_count: int = 0
    niche: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None

class UserSession(BaseModel):
    model_config = ConfigDict(extra="ignore")
    session_id: str
    user_id: str
    session_token: str
    expires_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Income(BaseModel):
    model_config = ConfigDict(extra="ignore")
    income_id: str = Field(default_factory=lambda: f"inc_{uuid.uuid4().hex[:12]}")
    user_id: str
    source: str
    platform: str
    amount: float
    date: datetime
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class IncomeCreate(BaseModel):
    source: str
    platform: str
    amount: float
    date: str
    notes: Optional[str] = None

# CRM Pipeline Stages
DEAL_STAGES = ["lead", "negotiating", "confirmed", "content_delivered", "payment_pending", "paid"]

class Deal(BaseModel):
    model_config = ConfigDict(extra="ignore")
    deal_id: str = Field(default_factory=lambda: f"deal_{uuid.uuid4().hex[:12]}")
    user_id: str
    brand_name: str
    platform: str  # youtube, instagram
    deliverable_type: str  # video, reel, post, story
    deal_value: float
    stage: str = "lead"  # CRM pipeline stage
    payment_due_date: Optional[datetime] = None
    contract_url: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class DealCreate(BaseModel):
    brand_name: str
    platform: str
    deliverable_type: str
    deal_value: float
    stage: str = "lead"
    payment_due_date: Optional[str] = None
    contract_url: Optional[str] = None
    notes: Optional[str] = None

class DealUpdate(BaseModel):
    brand_name: Optional[str] = None
    platform: Optional[str] = None
    deliverable_type: Optional[str] = None
    deal_value: Optional[float] = None
    stage: Optional[str] = None
    payment_due_date: Optional[str] = None
    contract_url: Optional[str] = None
    notes: Optional[str] = None

class ContentRevenue(BaseModel):
    model_config = ConfigDict(extra="ignore")
    content_id: str = Field(default_factory=lambda: f"content_{uuid.uuid4().hex[:12]}")
    user_id: str
    platform: str
    content_type: str
    views: int
    engagement_rate: float
    revenue: float
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ContentRevenueCreate(BaseModel):
    platform: str
    content_type: str
    views: int
    engagement_rate: float
    revenue: float

# GST-Compliant Invoice Model
class Invoice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    invoice_id: str = Field(default_factory=lambda: f"INV-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}")
    user_id: str
    # Creator details
    creator_name: str
    creator_address: Optional[str] = None
    creator_gstin: Optional[str] = None
    # Client details
    client_name: str
    client_address: Optional[str] = None
    client_gstin: Optional[str] = None
    # Invoice details
    invoice_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    description: str
    sac_code: str = "998361"  # SAC code for influencer/advertising services
    # Amounts
    taxable_value: float
    cgst_rate: float = 9.0
    sgst_rate: float = 9.0
    igst_rate: float = 0.0  # Use IGST for inter-state
    cgst_amount: float = 0.0
    sgst_amount: float = 0.0
    igst_amount: float = 0.0
    total_tax: float = 0.0
    total_amount: float = 0.0
    # Status
    status: str = "generated"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class InvoiceCreate(BaseModel):
    creator_name: str
    creator_address: Optional[str] = None
    creator_gstin: Optional[str] = None
    client_name: str
    client_address: Optional[str] = None
    client_gstin: Optional[str] = None
    description: str
    sac_code: str = "998361"
    taxable_value: float
    is_igst: bool = False  # True for inter-state supply
    gst_rate: float = 18.0  # GST rate (5, 12, 18, or 28)

class PricingSuggestionRequest(BaseModel):
    follower_count: int
    engagement_rate: float
    platform: str
    content_type: str

class AccessCodeRequest(BaseModel):
    code: str

# Milestones - Only realistic achievable ones
MILESTONES = [
    {"id": "first_deal", "name": "First Deal Logged", "condition": "deals >= 1"},
    {"id": "revenue_10k", "name": "First ₹10,000 Earned", "condition": "revenue >= 10000"},
    {"id": "first_paid", "name": "First Paid Brand Collaboration", "condition": "paid_deals >= 1"},
]

# ==================== AUTH HELPERS ====================

async def get_current_user(request: Request) -> dict:
    """Get current user from session token in cookies or Authorization header"""
    session_token = request.cookies.get("session_token")
    
    if not session_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            session_token = auth_header.split(" ")[1]
    
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    session_doc = await db.user_sessions.find_one(
        {"session_token": session_token},
        {"_id": 0}
    )
    
    if not session_doc:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    expires_at = session_doc["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")
    
    user_doc = await db.users.find_one(
        {"user_id": session_doc["user_id"]},
        {"_id": 0}
    )
    
    if not user_doc:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user_doc

# ==================== AUTH ENDPOINTS ====================

@api_router.post("/auth/session")
async def create_session(request: Request, response: Response):
    """Exchange session_id from Emergent Auth for a session token"""
    body = await request.json()
    session_id = body.get("session_id")
    
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    
    async with httpx.AsyncClient() as client_http:
        auth_response = await client_http.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": session_id}
        )
    
    if auth_response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session_id")
    
    auth_data = auth_response.json()
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    
    existing_user = await db.users.find_one({"email": auth_data["email"]}, {"_id": 0})
    
    if existing_user:
        user_id = existing_user["user_id"]
    else:
        new_user = {
            "user_id": user_id,
            "email": auth_data["email"],
            "name": auth_data["name"],
            "picture": auth_data.get("picture"),
            "early_access": False,
            "onboarding_complete": False,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.users.insert_one(new_user)
    
    session_token = f"sess_{uuid.uuid4().hex}"
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    
    session_doc = {
        "session_id": str(uuid.uuid4()),
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.user_sessions.insert_one(session_doc)
    
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=7 * 24 * 60 * 60
    )
    
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return user_doc

@api_router.get("/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Get current authenticated user"""
    return user

@api_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    """Logout and clear session"""
    session_token = request.cookies.get("session_token")
    
    if session_token:
        await db.user_sessions.delete_one({"session_token": session_token})
    
    response.delete_cookie(key="session_token", path="/", secure=True, samesite="none")
    return {"message": "Logged out successfully"}

# ==================== ACCESS CODE / PAYWALL ====================

@api_router.post("/auth/verify-access-code")
async def verify_access_code(data: AccessCodeRequest, user: dict = Depends(get_current_user)):
    """Verify early access code"""
    if data.code == "FIRST100":
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"early_access": True}}
        )
        return {"success": True, "message": "Early access granted!"}
    else:
        return {"success": False, "message": "Invalid access code"}

@api_router.get("/auth/access-status")
async def get_access_status(user: dict = Depends(get_current_user)):
    """Get user's access status"""
    return {
        "early_access": user.get("early_access", False),
        "onboarding_complete": user.get("onboarding_complete", False)
    }

# ==================== CREATOR PROFILE ====================

@api_router.get("/profile")
async def get_profile(user: dict = Depends(get_current_user)):
    """Get creator profile"""
    profile = await db.creator_profiles.find_one(
        {"user_id": user["user_id"]},
        {"_id": 0}
    )
    return profile

@api_router.post("/profile")
async def create_or_update_profile(profile_data: CreatorProfileCreate, user: dict = Depends(get_current_user)):
    """Create or update creator profile"""
    # Auto-detect platform from links
    detected_platform = None
    if profile_data.youtube_link and profile_data.instagram_handle:
        detected_platform = "both"
    elif profile_data.youtube_link:
        detected_platform = "youtube"
    elif profile_data.instagram_handle:
        detected_platform = "instagram"
    
    profile_doc = {
        "user_id": user["user_id"],
        **profile_data.model_dump(),
        "detected_platform": detected_platform,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    existing = await db.creator_profiles.find_one({"user_id": user["user_id"]})
    
    if existing:
        await db.creator_profiles.update_one(
            {"user_id": user["user_id"]},
            {"$set": profile_doc}
        )
    else:
        profile_doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.creator_profiles.insert_one(profile_doc)
    
    # Mark onboarding complete
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"onboarding_complete": True}}
    )
    
    result = await db.creator_profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return result

# ==================== INCOME ENDPOINTS ====================

@api_router.get("/income", response_model=List[dict])
async def get_income(user: dict = Depends(get_current_user)):
    """Get all income records for current user"""
    income_list = await db.income.find(
        {"user_id": user["user_id"]},
        {"_id": 0}
    ).sort("date", -1).to_list(1000)
    return income_list

@api_router.post("/income")
async def create_income(income_data: IncomeCreate, user: dict = Depends(get_current_user)):
    """Create a new income record"""
    income = Income(
        user_id=user["user_id"],
        source=income_data.source,
        platform=income_data.platform,
        amount=income_data.amount,
        date=datetime.fromisoformat(income_data.date.replace('Z', '+00:00')),
        notes=income_data.notes
    )
    
    doc = income.model_dump()
    doc['date'] = doc['date'].isoformat()
    doc['created_at'] = doc['created_at'].isoformat()
    
    await db.income.insert_one(doc)
    doc.pop('_id', None)
    return doc

@api_router.delete("/income/{income_id}")
async def delete_income(income_id: str, user: dict = Depends(get_current_user)):
    """Delete an income record"""
    result = await db.income.delete_one({"income_id": income_id, "user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Income not found")
    return {"message": "Income deleted"}

# ==================== DEALS ENDPOINTS (CRM PIPELINE) ====================

@api_router.get("/deals", response_model=List[dict])
async def get_deals(user: dict = Depends(get_current_user)):
    """Get all deals for current user"""
    deals = await db.deals.find(
        {"user_id": user["user_id"]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(1000)
    return deals

@api_router.get("/deals/pipeline")
async def get_deals_pipeline(user: dict = Depends(get_current_user)):
    """Get deals organized by pipeline stage"""
    deals = await db.deals.find(
        {"user_id": user["user_id"]},
        {"_id": 0}
    ).to_list(1000)
    
    pipeline = {stage: [] for stage in DEAL_STAGES}
    for deal in deals:
        stage = deal.get("stage", "lead")
        if stage in pipeline:
            pipeline[stage].append(deal)
    
    return pipeline

@api_router.post("/deals")
async def create_deal(deal_data: DealCreate, user: dict = Depends(get_current_user)):
    """Create a new deal"""
    deal = Deal(
        user_id=user["user_id"],
        brand_name=deal_data.brand_name,
        platform=deal_data.platform,
        deliverable_type=deal_data.deliverable_type,
        deal_value=deal_data.deal_value,
        stage=deal_data.stage,
        payment_due_date=datetime.fromisoformat(deal_data.payment_due_date.replace('Z', '+00:00')) if deal_data.payment_due_date else None,
        contract_url=deal_data.contract_url,
        notes=deal_data.notes
    )
    
    doc = deal.model_dump()
    if doc['payment_due_date']:
        doc['payment_due_date'] = doc['payment_due_date'].isoformat()
    doc['created_at'] = doc['created_at'].isoformat()
    
    await db.deals.insert_one(doc)
    doc.pop('_id', None)
    return doc

@api_router.put("/deals/{deal_id}")
async def update_deal(deal_id: str, deal_data: DealUpdate, user: dict = Depends(get_current_user)):
    """Update a deal"""
    update_dict = {k: v for k, v in deal_data.model_dump().items() if v is not None}
    
    if 'payment_due_date' in update_dict and update_dict['payment_due_date']:
        update_dict['payment_due_date'] = datetime.fromisoformat(update_dict['payment_due_date'].replace('Z', '+00:00')).isoformat()
    
    # Get current deal to check stage change
    current_deal = await db.deals.find_one({"deal_id": deal_id, "user_id": user["user_id"]}, {"_id": 0})
    
    if not current_deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    
    # If deal is being marked as paid, add to income
    if update_dict.get("stage") == "paid" and current_deal.get("stage") != "paid":
        income_doc = {
            "income_id": f"inc_{uuid.uuid4().hex[:12]}",
            "user_id": user["user_id"],
            "source": "brand_deal",
            "platform": current_deal["platform"],
            "amount": current_deal["deal_value"],
            "date": datetime.now(timezone.utc).isoformat(),
            "notes": f"Brand deal with {current_deal['brand_name']}",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.income.insert_one(income_doc)
    
    result = await db.deals.update_one(
        {"deal_id": deal_id, "user_id": user["user_id"]},
        {"$set": update_dict}
    )
    
    updated_deal = await db.deals.find_one({"deal_id": deal_id}, {"_id": 0})
    return updated_deal

@api_router.put("/deals/{deal_id}/stage")
async def update_deal_stage(deal_id: str, request: Request, user: dict = Depends(get_current_user)):
    """Update deal stage (for drag and drop)"""
    body = await request.json()
    new_stage = body.get("stage")
    
    if new_stage not in DEAL_STAGES:
        raise HTTPException(status_code=400, detail="Invalid stage")
    
    current_deal = await db.deals.find_one({"deal_id": deal_id, "user_id": user["user_id"]}, {"_id": 0})
    
    if not current_deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    
    # If deal is being marked as paid, add to income
    if new_stage == "paid" and current_deal.get("stage") != "paid":
        income_doc = {
            "income_id": f"inc_{uuid.uuid4().hex[:12]}",
            "user_id": user["user_id"],
            "source": "brand_deal",
            "platform": current_deal["platform"],
            "amount": current_deal["deal_value"],
            "date": datetime.now(timezone.utc).isoformat(),
            "notes": f"Brand deal with {current_deal['brand_name']}",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.income.insert_one(income_doc)
    
    await db.deals.update_one(
        {"deal_id": deal_id, "user_id": user["user_id"]},
        {"$set": {"stage": new_stage}}
    )
    
    return {"message": "Stage updated", "stage": new_stage}

@api_router.delete("/deals/{deal_id}")
async def delete_deal(deal_id: str, user: dict = Depends(get_current_user)):
    """Delete a deal"""
    result = await db.deals.delete_one({"deal_id": deal_id, "user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Deal not found")
    return {"message": "Deal deleted"}

# ==================== CONTENT REVENUE ENDPOINTS ====================

@api_router.get("/content", response_model=List[dict])
async def get_content_revenue(user: dict = Depends(get_current_user)):
    """Get all content revenue records"""
    content = await db.content_revenue.find(
        {"user_id": user["user_id"]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(1000)
    return content

@api_router.post("/content")
async def create_content_revenue(content_data: ContentRevenueCreate, user: dict = Depends(get_current_user)):
    """Create a new content revenue record"""
    content = ContentRevenue(
        user_id=user["user_id"],
        platform=content_data.platform,
        content_type=content_data.content_type,
        views=content_data.views,
        engagement_rate=content_data.engagement_rate,
        revenue=content_data.revenue
    )
    
    doc = content.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    
    await db.content_revenue.insert_one(doc)
    doc.pop('_id', None)
    return doc

@api_router.delete("/content/{content_id}")
async def delete_content_revenue(content_id: str, user: dict = Depends(get_current_user)):
    """Delete a content revenue record"""
    result = await db.content_revenue.delete_one({"content_id": content_id, "user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Content not found")
    return {"message": "Content deleted"}

# ==================== GST INVOICE ENDPOINTS ====================

@api_router.get("/invoices", response_model=List[dict])
async def get_invoices(user: dict = Depends(get_current_user)):
    """Get all invoices for current user"""
    invoices = await db.invoices.find(
        {"user_id": user["user_id"]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(1000)
    return invoices

@api_router.post("/invoices")
async def create_invoice(invoice_data: InvoiceCreate, user: dict = Depends(get_current_user)):
    """Create a new GST-compliant invoice"""
    taxable = invoice_data.taxable_value
    
    if invoice_data.is_igst:
        igst_rate = 18.0
        igst_amount = round(taxable * igst_rate / 100, 2)
        cgst_amount = 0.0
        sgst_amount = 0.0
        cgst_rate = 0.0
        sgst_rate = 0.0
    else:
        cgst_rate = 9.0
        sgst_rate = 9.0
        cgst_amount = round(taxable * cgst_rate / 100, 2)
        sgst_amount = round(taxable * sgst_rate / 100, 2)
        igst_rate = 0.0
        igst_amount = 0.0
    
    total_tax = cgst_amount + sgst_amount + igst_amount
    total_amount = taxable + total_tax
    
    invoice = Invoice(
        user_id=user["user_id"],
        creator_name=invoice_data.creator_name,
        creator_address=invoice_data.creator_address,
        creator_gstin=invoice_data.creator_gstin,
        client_name=invoice_data.client_name,
        client_address=invoice_data.client_address,
        client_gstin=invoice_data.client_gstin,
        description=invoice_data.description,
        sac_code=invoice_data.sac_code,
        taxable_value=taxable,
        cgst_rate=cgst_rate,
        sgst_rate=sgst_rate,
        igst_rate=igst_rate,
        cgst_amount=cgst_amount,
        sgst_amount=sgst_amount,
        igst_amount=igst_amount,
        total_tax=total_tax,
        total_amount=total_amount
    )
    
    doc = invoice.model_dump()
    doc['invoice_date'] = doc['invoice_date'].isoformat()
    doc['created_at'] = doc['created_at'].isoformat()
    
    await db.invoices.insert_one(doc)
    doc.pop('_id', None)
    return doc

@api_router.delete("/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str, user: dict = Depends(get_current_user)):
    """Delete an invoice"""
    result = await db.invoices.delete_one({"invoice_id": invoice_id, "user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {"message": "Invoice deleted"}

# ==================== DASHBOARD ENDPOINTS ====================

@api_router.get("/dashboard/stats")
async def get_dashboard_stats(user: dict = Depends(get_current_user)):
    """Get dashboard statistics"""
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Get income from income collection
    all_income = await db.income.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    
    # Get all deals
    all_deals = await db.deals.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    
    # Only count PAID deals for revenue calculations
    paid_deal_values = [d['deal_value'] for d in all_deals if d.get('stage') == 'paid']
    
    # Total revenue = income + paid deals only
    income_total = sum(i['amount'] for i in all_income)
    paid_deals_total = sum(paid_deal_values)
    total_revenue = income_total + paid_deals_total
    
    # Month revenue = this month's income + this month's paid deals only
    month_income = sum(
        i['amount'] for i in all_income 
        if datetime.fromisoformat(i['date']).replace(tzinfo=timezone.utc) >= month_start
    )
    
    # For paid deals, check if they have a payment date or created_at in current month
    month_paid_deals = sum(
        d['deal_value'] for d in all_deals 
        if d.get('stage') == 'paid' and (
            (d.get('payment_date') and datetime.fromisoformat(d['payment_date']).replace(tzinfo=timezone.utc) >= month_start) or
            (d.get('created_at') and datetime.fromisoformat(d['created_at']).replace(tzinfo=timezone.utc) >= month_start)
        )
    )
    month_revenue = month_income + month_paid_deals
    
    active_deals = len([d for d in all_deals if d.get('stage') in ['lead', 'negotiating', 'confirmed', 'content_delivered', 'payment_pending']])
    paid_deals = len([d for d in all_deals if d.get('stage') == 'paid'])
    
    # Pending payments - only unpaid deals
    pending_payments = sum(
        d['deal_value'] for d in all_deals 
        if d.get('stage') in ['confirmed', 'content_delivered', 'payment_pending']
    )
    
    revenue_by_source = {}
    for income in all_income:
        source = income['source']
        revenue_by_source[source] = revenue_by_source.get(source, 0) + income['amount']
    # Add paid deals as "brand_deal" source
    if paid_deals_total > 0:
        revenue_by_source['brand_deal'] = revenue_by_source.get('brand_deal', 0) + paid_deals_total
    
    monthly_revenue = []
    for i in range(5, -1, -1):
        month = now - timedelta(days=30 * i)
        month_name = month.strftime('%b')
        month_total = sum(
            inc['amount'] for inc in all_income
            if datetime.fromisoformat(inc['date']).strftime('%Y-%m') == month.strftime('%Y-%m')
        )
        # Add paid deals for that month
        month_total += sum(
            d['deal_value'] for d in all_deals
            if d.get('stage') == 'paid' and d.get('created_at') and
            datetime.fromisoformat(d['created_at']).strftime('%Y-%m') == month.strftime('%Y-%m')
        )
        monthly_revenue.append({"month": month_name, "revenue": month_total})
    
    return {
        "total_revenue": total_revenue,
        "month_revenue": month_revenue,
        "active_deals": active_deals,
        "paid_deals": paid_deals,
        "pending_payments": pending_payments,
        "revenue_by_source": [{"name": k, "value": v} for k, v in revenue_by_source.items()],
        "monthly_revenue": monthly_revenue
    }

@api_router.get("/dashboard/insights")
async def get_creator_insights(user: dict = Depends(get_current_user)):
    """Get creator insights for dashboard"""
    all_income = await db.income.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    all_deals = await db.deals.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    profile = await db.creator_profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
    
    total_revenue = sum(i['amount'] for i in all_income)
    total_deals = len(all_deals)
    paid_deals = len([d for d in all_deals if d.get('stage') == 'paid'])
    avg_deal_value = total_revenue / paid_deals if paid_deals > 0 else 0
    
    # Revenue by platform
    platform_revenue = {}
    for income in all_income:
        platform = income['platform']
        platform_revenue[platform] = platform_revenue.get(platform, 0) + income['amount']
    
    # Determine top platform - use detected_platform if no income data
    if platform_revenue:
        top_platform = max(platform_revenue.items(), key=lambda x: x[1])[0]
    elif profile and profile.get('detected_platform'):
        detected = profile['detected_platform']
        if detected == 'both':
            top_platform = 'YouTube & Instagram'
        else:
            top_platform = detected.capitalize()
    else:
        top_platform = "N/A"
    
    return {
        "total_deals_closed": paid_deals,
        "total_revenue": total_revenue,
        "average_deal_value": round(avg_deal_value, 2),
        "top_platform": top_platform,
        "platform_revenue": [{"platform": k, "revenue": v} for k, v in platform_revenue.items()]
    }

@api_router.get("/dashboard/milestones")
async def get_milestones(user: dict = Depends(get_current_user)):
    """Get creator milestones - only return achieved ones"""
    all_income = await db.income.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    all_deals = await db.deals.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    
    total_revenue = sum(i['amount'] for i in all_income)
    total_deals = len(all_deals)
    paid_deals = len([d for d in all_deals if d.get('stage') == 'paid'])
    
    achieved = []
    
    # Only add milestones that are achieved
    if total_deals >= 1:
        achieved.append({"id": "first_deal", "name": "First Deal Logged", "achieved": True})
    
    if total_revenue >= 10000:
        achieved.append({"id": "revenue_10k", "name": "First ₹10,000 Earned", "achieved": True})
    
    if paid_deals >= 1:
        achieved.append({"id": "first_paid", "name": "First Paid Brand Collaboration", "achieved": True})
    
    return achieved

@api_router.get("/dashboard/upcoming-payments")
async def get_upcoming_payments(user: dict = Depends(get_current_user)):
    """Get upcoming payment reminders - includes all unpaid deals with due dates"""
    now = datetime.now(timezone.utc)
    
    # Get all deals that are NOT paid (excludes only 'paid' stage)
    deals = await db.deals.find(
        {"user_id": user["user_id"], "stage": {"$ne": "paid"}},
        {"_id": 0}
    ).to_list(1000)
    
    payments = []
    for deal in deals:
        if deal.get('payment_due_date'):
            due_date = datetime.fromisoformat(deal['payment_due_date'])
            if due_date.tzinfo is None:
                due_date = due_date.replace(tzinfo=timezone.utc)
            
            days_until = (due_date - now).days
            
            status = "upcoming"
            if days_until < 0:
                status = "overdue"
            elif days_until <= 3:
                status = "due_soon"
            
            payments.append({
                "deal_id": deal['deal_id'],
                "brand_name": deal['brand_name'],
                "amount": deal['deal_value'],
                "due_date": deal['payment_due_date'],
                "days_until": days_until,
                "status": status,
                "stage": deal.get('stage', 'lead')
            })
    
    payments.sort(key=lambda x: x['days_until'])
    return payments

@api_router.get("/dashboard/cashflow")
async def get_cashflow_timeline(user: dict = Depends(get_current_user)):
    """Get cashflow timeline for next 4 weeks"""
    now = datetime.now(timezone.utc)
    
    # Get all unpaid deals
    deals = await db.deals.find(
        {"user_id": user["user_id"], "stage": {"$ne": "paid"}},
        {"_id": 0}
    ).to_list(1000)
    
    weeks = []
    for i in range(4):
        week_start = now + timedelta(weeks=i)
        week_end = week_start + timedelta(days=7)
        
        week_payments = sum(
            d['deal_value'] for d in deals
            if d.get('payment_due_date') and 
            week_start <= datetime.fromisoformat(d['payment_due_date']).replace(tzinfo=timezone.utc) < week_end
        )
        
        weeks.append({
            "week": f"Week {i + 1}",
            "amount": week_payments
        })
    
    return weeks

# ==================== AI PRICING ENDPOINT ====================

@api_router.post("/ai/pricing-suggestion")
async def get_pricing_suggestion(data: PricingSuggestionRequest, user: dict = Depends(get_current_user)):
    """Get AI-powered pricing suggestion using Gemini 3 Flash"""
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    
    api_key = os.environ.get('EMERGENT_LLM_KEY')
    if not api_key:
        raise HTTPException(status_code=500, detail="AI service not configured")
    
    chat = LlmChat(
        api_key=api_key,
        session_id=f"pricing_{user['user_id']}_{uuid.uuid4().hex[:8]}",
        system_message="""You are a brand deal pricing expert for content creators in India. 
        Based on the creator's metrics, suggest a fair price range for brand collaborations.
        Consider market rates for Indian creators, engagement quality, and platform specifics.
        Always respond with a JSON object containing: min_price, max_price, reasoning.
        Prices should be in Indian Rupees (₹)."""
    ).with_model("gemini", "gemini-3-flash-preview")
    
    prompt = f"""Suggest a brand deal price range for a creator with these metrics:
    - Platform: {data.platform}
    - Content Type: {data.content_type}
    - Follower Count: {data.follower_count:,}
    - Engagement Rate: {data.engagement_rate}%
    
    Respond with a JSON object: {{"min_price": number, "max_price": number, "reasoning": "brief explanation"}}"""
    
    user_message = UserMessage(text=prompt)
    
    try:
        response = await chat.send_message(user_message)
        
        import json
        import re
        
        json_match = re.search(r'\{[^{}]*\}', response)
        if json_match:
            result = json.loads(json_match.group())
            return {
                "min_price": result.get("min_price", 10000),
                "max_price": result.get("max_price", 50000),
                "reasoning": result.get("reasoning", "Based on your metrics and market rates.")
            }
        else:
            return {
                "min_price": 10000,
                "max_price": 50000,
                "reasoning": response
            }
    except Exception as e:
        logger.error(f"AI pricing error: {str(e)}")
        base_price = data.follower_count * 0.01
        engagement_multiplier = 1 + (data.engagement_rate / 10)
        min_price = int(base_price * engagement_multiplier * 0.8)
        max_price = int(base_price * engagement_multiplier * 1.2)
        
        return {
            "min_price": max(5000, min_price),
            "max_price": max(10000, max_price),
            "reasoning": "Estimated based on follower count and engagement rate."
        }

# ==================== BASIC ROUTES ====================

@api_router.get("/")
async def root():
    return {"message": "CreatorOS API"}

@api_router.get("/health")
async def health_check():
    return {"status": "healthy"}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
