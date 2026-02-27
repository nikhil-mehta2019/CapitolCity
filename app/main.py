import json
import logging
from fastapi import FastAPI, Depends, Header, HTTPException, APIRouter
from jose import jwt, JWTError

from app.config import JWT_SECRET, ALGORITHM
from app.hubspot import (
    get_deal,
    get_distinct_permit_stages,
    get_sales_rep_name_by_email,
    search_deals_by_sales_rep,
    get_pinned_note_for_deal,
    get_all_notes,
    get_note_body_by_id,
    get_permit_stages_by_sales_rep,
    normalize_permit_stage,
    get_contact_by_email,
    get_deals_by_contact_id,
    get_sales_reps_under_pm,
    get_gm_assigned_company,
    get_gm_dashboard_data
)

logger = logging.getLogger(__name__)

# ------------------------------------------------
# JWT Security Middleware
# ------------------------------------------------
# Purpose:
# - Protect all /api routes
# - Requires Authorization: Bearer <JWT>
# - Validates signature and expiration
# ------------------------------------------------

async def verify_jwt(authorization: str = Header(None)):
    if not JWT_SECRET:
        raise HTTPException(status_code=500, detail="JWT secret not configured")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.split(" ")[1]

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ------------------------------------------------
# FastAPI App Initialization
# ------------------------------------------------

app = FastAPI(title="HubSpot Middleware API")

# Protected router for all secured APIs
api_router = APIRouter(
    prefix="/api",
    dependencies=[Depends(verify_jwt)]
)

# ------------------------------------------------
# Health Check API
# ------------------------------------------------
# Purpose:
# - Verifies that the FastAPI service is running
# - Used for deployment checks and monitoring
# - Does NOT require JWT
# ------------------------------------------------

@app.get("/")
def root():
    return {"status": "HubSpot middleware running"}


# ------------------------------------------------
# Core Data API: Get All Deals for a Sales Rep
# ------------------------------------------------
# Purpose:
# - Fetch all permits (Deals) belonging to a specific Sales Rep
# - Filters HubSpot data where:
#     {Sales Rep} = sales_rep
# - Foundation API for dashboard, listings, filtering
# - JWT Required
# ------------------------------------------------

@api_router.get("/deals/by-sales-rep/{sales_rep}")
async def get_deals_for_rep(sales_rep: str):
    return await search_deals_by_sales_rep(sales_rep)


# ------------------------------------------------
# Dashboard Summary API
# ------------------------------------------------
# Purpose:
# - Builds a summary of permits grouped by Permit Stage
# - Powers dashboard cards
# - JWT Required
# ------------------------------------------------

@api_router.get("/dashboard/{sales_rep}")
async def dashboard_summary(sales_rep: str):
    deals = await search_deals_by_sales_rep(sales_rep)
    return format_dashboard_response(deals)


# ------------------------------------------------
# Deal Detail API
# ------------------------------------------------
# Purpose:
# - Fetch a single permit (Deal) by Deal ID
# - Returns formatted detail view
# - Includes pinned note
# - JWT Required
# ------------------------------------------------

@api_router.get("/deal/{deal_id}")
async def fetch_deal(deal_id: str):
    deal_raw = await get_deal(deal_id)
    props = deal_raw.get("properties", {})

    pinned_note = await get_pinned_note_for_deal(deal_id)

    return {
        "info": {
            "deal_name": props.get("dealname") or "Unnamed Deal",
            "address": props.get("project_address") or "NA",
            "jurisdiction": props.get("juridstiction") or "NA",
            "general_contractor": props.get("general_contractor") or "NA",
            "finance": props.get("finnace") or "NA",
            "kick_off_invoice": format_invoice_status(props.get("kickoff_invoice_status")),
            "start_date": format_date(props.get("createdate")),
            "dependency": props.get("dependency") or "NA"
        },
        "documents": {
            "floor_plan": format_standard_doc(props.get("floor_plan")),
            "pier_plan": format_standard_doc(props.get("pier_plan")),
            "chassis_plan": format_standard_doc(props.get("chassis_plan")),
            "elevations": format_standard_doc(props.get("elevations")),
            "sprinkler_plan": format_standard_doc(props.get("sprinkler_plan")),
            "pending_articles": props.get("pending_articles") or "None"
        },
        "updates": {
            "pinned_note": pinned_note.get("body") if pinned_note else "No pinned updates."
        }
    }


# ------------------------------------------------
# API: Get Deals by Sales Rep AND Permit Stage
# ------------------------------------------------
# Purpose:
# - Filters HubSpot Deals by:
#     {Sales Rep} and {Permit Stage}
# - Used for stage drill-down
# - JWT Required
# ------------------------------------------------

@api_router.get("/deals/{sales_rep}/stage/{permit_stage}")
async def get_deals_by_stage(sales_rep: str, permit_stage: str):
    deals = await search_deals_by_sales_rep(sales_rep)

    filtered = []
    for d in deals:
        if (d.get("permit_stage") or "").lower() == permit_stage.lower():
            filtered.append(d)

    return filtered


# ------------------------------------------------
# Fetch All Notes API
# ------------------------------------------------
# Purpose:
# - Retrieve notes from HubSpot account
# - Used for debugging / validation
# - JWT Required
# ------------------------------------------------

@api_router.get("/notes")
async def fetch_all_notes(limit: int = 100, after: str | None = None):
    return await get_all_notes(limit, after)


# ------------------------------------------------
# Fetch Note Body API
# ------------------------------------------------
# Purpose:
# - Retrieve content of a specific HubSpot note
# - JWT Required
# ------------------------------------------------

@api_router.get("/notes/{note_id}")
async def fetch_note_body(note_id: str):
    return await get_note_body_by_id(note_id)


# ------------------------------------------------
# Distinct Permit Stages API
# ------------------------------------------------
# Purpose:
# - Returns unique normalized permit stages
# - Used for UI filter dropdown
# - JWT Required
# ------------------------------------------------

@api_router.get("/deals/{sales_rep}/permit-stages/distinct")
async def distinct_permit_stages(sales_rep: str):
    return await get_distinct_permit_stages(sales_rep)


# ------------------------------------------------
# Dashboard by Email API
# ------------------------------------------------
# Purpose:
# - Resolve email → sales rep
# - Returns dashboard summary
# - Used for Wix integration
# - JWT Required
# ------------------------------------------------

@api_router.get("/dashboard/email/{user_email}")
async def dashboard_summary_by_email(user_email: str):
    sales_rep_name = await get_sales_rep_name_by_email(user_email)

    if not sales_rep_name:
        return {
            "error": "User not linked",
            "summary": {"pre_submittal": 0, "post_submittal": 0, "completed": 0},
            "alerts": {"pre_submittal": [], "post_submittal": []},
            "permits": []
        }

    return await dashboard_summary(sales_rep_name)


# ------------------------------------------------
# Verify Wix Contact API
# ------------------------------------------------
# Purpose:
# - Checks if Wix email exists in HubSpot
# - Returns dashboard data if matched
# - JWT Required
# ------------------------------------------------

@api_router.get("/verify-wix-contact/{email}")
async def verify_wix_contact_email(email: str):
    contact = await get_contact_by_email(email)

    if contact:
        props = contact.get("properties", {})
        deals = await search_deals_by_sales_rep(
            f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
        )
        return format_dashboard_response(deals)


# ------------------------------------------------
# Project Manager Sales Reps API
# ------------------------------------------------
# Purpose:
# - Returns sales reps under a project manager
# - JWT Required
# ------------------------------------------------

@api_router.get("/project-manager/{pm_email}/sales-reps")
async def sales_reps_for_pm(pm_email: str):
    reps = await get_sales_reps_under_pm(pm_email)
    return {
        "project_manager": pm_email,
        "sales_reps": reps,
        "count": len(reps)
    }


# ------------------------------------------------
# GM Dashboard API
# ------------------------------------------------
# Purpose:
# - Returns company-level aggregated dashboard
# - JWT Required
# ------------------------------------------------

@api_router.get("/gm-dashboard/{email}")
async def gm_dashboard_summary(email: str):
    company_name = await get_gm_assigned_company(email)

    if not company_name:
        return {
            "error": "Configuration Error",
            "summary": {"pre_submittal": 0, "post_submittal": 0, "completed": 0},
            "agents": [],
            "permits": []
        }

    return await get_gm_dashboard_data(company_name)


# Attach secured router
app.include_router(api_router)