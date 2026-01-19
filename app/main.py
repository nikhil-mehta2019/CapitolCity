from fastapi import FastAPI
from .hubspot import get_deal, search_deals_by_sales_rep

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

    summary = {}
    for d in deals:
        stage = d.get("permit_stage") or "Unknown"
        summary[stage] = summary.get(stage, 0) + 1

    return summary


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
    return deal

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
