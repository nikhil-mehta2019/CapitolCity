from fastapi import FastAPI
from app.hubspot import (
    get_deal,
    get_distinct_permit_stages,
    search_deals_by_sales_rep,
    get_pinned_note_for_deal,
    get_all_notes,
    get_note_body_by_id,
    get_permit_stages_by_sales_rep,
    normalize_permit_stage
)

app = FastAPI(title="HubSpot Middleware API")

# ------------------------------------------------
# Health Check API
# ------------------------------------------------
# Purpose:
# - Verifies that the FastAPI service is running
# - Used for deployment checks and monitoring
# - Does not call HubSpot
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
# - This is the foundation API for:
#   - Permit listing
#   - Dashboard summary
#   - Stage-based filtering
#   - Table views in the portal
# ------------------------------------------------

@app.get("/api/deals/by-sales-rep/{sales_rep}")
async def get_deals_for_rep(sales_rep: str):
    return await search_deals_by_sales_rep(sales_rep)


# ------------------------------------------------
# Dashboard Summary API
# ------------------------------------------------
# Purpose:
# - Builds a summary of permits grouped by Permit Stage
# - Uses the core Sales Rep API internally
# - Returns counts for each stage
# - Powers the dashboard cards view
# ------------------------------------------------

@app.get("/api/dashboard/{sales_rep}")
async def dashboard_summary(sales_rep: str):
    deals = await search_deals_by_sales_rep(sales_rep)

    summary = {
        "pre_submittal": 0,
        "post_submittal": 0,
        "completed": 0
    }

    alerts = {
        "pre_submittal": [],
        "post_submittal": []
    }

    permits = []

    for d in deals:
        props = d.get("properties", {})
        stage = normalize_permit_stage(
            props.get("permit_stage") or d.get("permit_stage")
        )

        # ---------------- KPI COUNTS ----------------
        if stage == "Pre-Submittal":
            summary["pre_submittal"] += 1
        elif stage == "Post-Submittal":
            summary["post_submittal"] += 1
        elif stage == "Issued" or stage == "Completed":
            summary["completed"] += 1

        # ---------------- ALERT CARDS ----------------
        alert_item = {
            "deal_id": d.get("id"),
            "project_name": props.get("dealname"),
            "date": props.get("hs_lastmodifieddate"),
            "description": props.get("description", "")
        }

        if stage == "Pre-Submittal":
            alerts["pre_submittal"].append(alert_item)

        if stage == "Post-Submittal":
            alerts["post_submittal"].append(alert_item)

        # ---------------- TABLE ROW ----------------
        permits.append({
            "deal_id": d.get("id"),
            "customer": props.get("dealname"),
            "stage": stage,
            "address": props.get("project_address"),
            "jurisdiction": props.get("jurisdiction"),
            "dependency": props.get("dependency")
        })

    return {
        "summary": summary,
        "alerts": alerts,
        "permits": permits
    }


# ------------------------------------------------
# Deal Detail API
# ------------------------------------------------
# Purpose:
# - Fetch a single permit (Deal) directly from HubSpot using Deal ID
# - Used for:
#   - Permit detail view
#   - Debugging and validation
#   - Support and verification of individual records
# - Returns raw HubSpot Deal data (can be cleaned later)
# ------------------------------------------------

@app.get("/api/deal/{deal_id}")
async def fetch_deal(deal_id: str):
    deal = await get_deal(deal_id)
    pinned_note = await get_pinned_note_for_deal(deal_id)

    return {
        "deal": deal,
        "pinned_note": pinned_note
    }

# ------------------------------------------------
# API: Get Deals by Sales Rep AND Permit Stage
# ------------------------------------------------
# Purpose:
# - Used when user clicks a Permit Stage card on the dashboard
# - Returns all permits under that stage for the logged-in Sales Rep
# - Filters HubSpot Deals by:
#     {Sales Rep} = sales_rep
#     {Permit Stage} = permit_stage
# - This powers the stage drill-down list/table in the portal
# ------------------------------------------------

@app.get("/api/deals/{sales_rep}/stage/{permit_stage}")
async def get_deals_by_stage(sales_rep: str, permit_stage: str):
    deals = await search_deals_by_sales_rep(sales_rep)

    filtered = []
    for d in deals:
        if (d.get("permit_stage") or "").lower() == permit_stage.lower():
            filtered.append(d)

    return filtered


# ------------------------------------------------
# Fetch All Notes (Account-wide) API
# ------------------------------------------------
# Purpose:
# - Retrieve notes from the HubSpot account with pagination support
# - Primarily used for debugging, validation, or internal review
# - Not intended for direct use in the permit dashboard UI
#
# Important:
# - This API fetches notes across the entire HubSpot account
# - Results are not filtered by Deal or Sales Rep
# - Access depends on permissions of the HubSpot Private App token
# ------------------------------------------------

@app.get("/api/notes")
async def fetch_all_notes(limit: int = 100, after: str | None = None):
    return await get_all_notes(limit, after)


# ------------------------------------------------
# API: Fetch Note Body by Note ID
# ------------------------------------------------
# Purpose:
# - Retrieve the content (body) of a single HubSpot note using its Note ID
# - Used to display pinned or linked notes in the permit detail view
# - This API is read-only and does not modify HubSpot data
#
# Important:
# - Note body availability depends on HubSpot portal configuration
# - Access is limited to notes readable by the Private App token
# ------------------------------------------------
@app.get("/api/notes/{note_id}")
async def fetch_note_body(note_id: str):
    return await get_note_body_by_id(note_id)

# ------------------------------------------------
# Distinct Permit Stages (for UI filters)
# ------------------------------------------------
@app.get("/api/deals/{sales_rep}/permit-stages/distinct")
async def distinct_permit_stages(sales_rep: str):
    return await get_distinct_permit_stages(sales_rep)
