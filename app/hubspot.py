import httpx
import json
import logging
from app.config import HUBSPOT_TOKEN, BASE_URL

# ------------------------------------------------
# Common headers for HubSpot API calls
# Uses Private App token (long-lived, no refresh)
# ------------------------------------------------
headers = {
    "Authorization": f"Bearer {HUBSPOT_TOKEN}",
    "Content-Type": "application/json"
}
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# ------------------------------------------------
# Get single Deal by Deal ID
# - Used for Deal detail view
# - Returns raw HubSpot deal object
# ------------------------------------------------
async def get_deal(deal_id: str):
    url = f"{BASE_URL}/crm/v3/objects/deals/{deal_id}"
    params = {
        "properties": [
            "dealname",
            "permit_stage",
            "jurisdiction",
            "project_address",
            "dependency",
            "sales_rep"
        ]
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()


# ------------------------------------------------
# Search Deals by Sales Rep
# - Core API used across dashboard and listings
# - Filters HubSpot Deals where {Sales Rep} matches
# - Returns only the `results` array (not raw response)
# ------------------------------------------------
async def search_deals_by_sales_rep(sales_rep: str):
    url = f"{BASE_URL}/crm/v3/objects/deals/search"

    payload = {
        "filterGroups": [
            {
                "filters": [
                    {
                        "propertyName": "sales_rep",
                        "operator": "EQ",
                        "value": sales_rep
                    }
                ]
            }
        ],
        "properties": [
            "dealname",
            "dealstage",
            "project_address",
            "juridstiction",     # ✅ must be here
            "dependency",
            "permit_number",
            "submittal_portal",
            "hs_lastmodifieddate"
        ],
        "limit": 100
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

        # HubSpot returns { results, paging }
        # We only return the list of deals
        return data.get("results", [])


# ------------------------------------------------
# Get pinned note for a Deal
# Important:
# - Pinned notes are NOT Deal properties
# - They are Notes (Engagements) associated to the Deal
# - We search notes linked to the deal and return the pinned one
# ------------------------------------------------
async def get_pinned_note_for_deal(deal_id: str):
    search_url = f"{BASE_URL}/crm/v3/objects/notes/search"

    search_payload = {
        "filterGroups": [
            {
                "filters": [
                    {
                        "propertyName": "associations.deal",
                        "operator": "EQ",
                        "value": deal_id
                    }
                ]
            }
        ],
        "sorts": ["-hs_createdate"],
        "limit": 1
    }

    async with httpx.AsyncClient() as client:
        search_resp = await client.post(
            search_url,
            json=search_payload,
            headers=headers
        )
        search_resp.raise_for_status()

        search_json = search_resp.json()

        # 🔴 LOG RAW SEARCH RESPONSE
        logger.info(
            "HubSpot NOTES SEARCH response:\n%s",
            json.dumps(search_json, indent=2)
        )

        notes = search_json.get("results", [])
        if not notes:
            return None

        note_id = notes[0]["id"]

        # ---- fetch full note ----
        detail_url = f"{BASE_URL}/crm/v3/objects/notes/{note_id}"
        detail_resp = await client.get(detail_url, headers=headers)
        detail_resp.raise_for_status()

        detail_json = detail_resp.json()

        # 🔴 LOG RAW NOTE DETAIL RESPONSE
        logger.info(
            "HubSpot NOTE DETAIL response:\n%s",
            json.dumps(detail_json, indent=2)
        )

    props = detail_json.get("properties", {})

    return {
        "id": note_id,
        "body": await get_note_body_by_id(note_id),
        "created_at": props.get("hs_createdate")
    }
async def get_all_notes(limit: int = 100, after: str | None = None):
    url = f"{BASE_URL}/crm/v3/objects/notes"
    params = {"limit": limit}

    if after:
        params["after"] = after

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

async def get_note_body_by_id(note_id: str):
    # Add the properties parameter to the URL to include the note body
    url = f"{BASE_URL}/crm/v3/objects/notes/{note_id}?properties=hs_note_body"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        
        # The body text is nested inside the 'properties' key
        note_body = data.get("properties", {}).get("hs_note_body")
        
        return note_body

# ------------------------------------------------
# Mapped from HubSpot Internal Names to Dashboard Categories: "Pre-Submittal", "Post-Submittal", "Completed"
# ------------------------------------------------
PERMIT_STAGE_MAP = {
    # Internal Name (from API)      : Display Name (from HubSpot UI)
    
    # --- Pre-Submittal Group ---
    "2909556468": "Fee Estimate (Permit Pipeline)",
    "appointmentscheduled": "Intake (Permit Pipeline)",
    "qualifiedtobuy": "Pre-Submittal (Permit Pipeline)",
    
    # --- Post-Submittal Group ---
    "presentationscheduled": "Submittal (Permit Pipeline)",
    
    # --- Completed Group ---
    "decisionmakerboughtin": "Approved (Permit Pipeline)",
    "contractsent": "Closed (Permit Pipeline)",
    
    # --- Other ---
    "closedlost": "Closed Lost (Permit Pipeline)"
}

def normalize_permit_stage(stage: str | None):
    if not stage:
        return "Unknown"
    # Strip whitespace and convert to string just in case
    key = str(stage).strip().lower()
    
    # Return mapped value, or default to the raw key if not found
    return PERMIT_STAGE_MAP.get(key, stage)

 # ------------------------------------------------
 # NEW: Get Permit Stage per Deal (by Sales Rep)
 # ------------------------------------------------
async def get_permit_stages_by_sales_rep(sales_rep: str):
    deals = await search_deals_by_sales_rep(sales_rep)

    return [
        {
            "deal_id": d.get("id"),
            "permit_stage": normalize_permit_stage(
                d.get("permit_stage") or d.get("properties", {}).get("permit_stage")
            )
        }
        for d in deals
    ]
 # ------------------------------------------------
 # NEW: Get distinct normalized permit stages
 # ------------------------------------------------
async def get_distinct_permit_stages(sales_rep: str):
    deals = await search_deals_by_sales_rep(sales_rep)

    stages = set()
    for d in deals:
        stage = normalize_permit_stage(
            d.get("permit_stage") or d.get("properties", {}).get("permit_stage")
        )
        if stage:
            stages.add(stage)

    return sorted(stages)
