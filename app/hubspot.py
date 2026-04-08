import asyncio
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
SALES_REP_CACHE = None
# ------------------------------------------------
# Get single Deal by Deal ID
# - Used for Deal detail view
# - Returns raw HubSpot deal object
# ------------------------------------------------
async def get_deal(deal_id: str):
    print("BASE_URL from config:", BASE_URL)
    print("Token loaded:", HUBSPOT_TOKEN is not None)
    print("Token preview:", HUBSPOT_TOKEN[:10] if HUBSPOT_TOKEN else None)
    url = f"{BASE_URL}/crm/v3/objects/deals/{deal_id}"
    print("Final URL:", url)
    params = {
        "properties": [
            "dealname",
            "dealstage",
            "permit_stage",
            "juridstiction",
            "project_address",
            "dependency",
            # --- New Fields for Detail View ---
            "general_contractor",      
            "finnace",                 
            "kickoff_invoice_status",  
            "project_start_date",      
            
            # --- Document Fields ---
            "floor_plan",              
            "pier_plan",               
            "chasis_plan",             
            "elevations",              
            "sprinkler_plan",          
            "pending_articles",        
            
            "sales_rep",
            "hs_pinned_engagement_id",

           
            "cd_set_status", 
            "site_plan_zoom_status", #Site Plan Meeting Status
            "requested_date",
            "eta", #SLA
            "customer_packet_status"

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
            "juridstiction",     # Keep this typo as in HubSpot
            "dependency",
            "permit_number",
            "submittal_portal",
            "hs_lastmodifieddate",
            "description"
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
async def get_pinned_note_for_deal(pinned_id: str):

    if not pinned_id:
        return None

    activity_types = {
        "notes": ["hs_note_body", "hs_timestamp"],
        "tasks": ["hs_task_subject", "hs_task_body", "hs_timestamp"],
        "meetings": ["hs_meeting_title", "hs_meeting_body", "hs_timestamp"],
        "calls": ["hs_call_title", "hs_call_body", "hs_timestamp"],
        "emails": ["hs_email_subject", "hs_email_text", "hs_timestamp"]
    }

    async with httpx.AsyncClient() as client:

        for activity, fields in activity_types.items():

            url = f"{BASE_URL}/crm/v3/objects/{activity}/{pinned_id}"

            params = {
                "properties": ",".join(fields)
            }

            resp = await client.get(url, headers=headers, params=params)

            if resp.status_code == 200:

                data = resp.json()
                props = data.get("properties", {})

                text = (
                    props.get("hs_note_body")
                    or props.get("hs_task_subject")
                    or props.get("hs_task_body")
                    or props.get("hs_meeting_title")
                    or props.get("hs_meeting_body")
                    or props.get("hs_call_title")
                    or props.get("hs_call_body")
                    or props.get("hs_email_subject")
                    or props.get("hs_email_text")
                    or ""
                )

                return {
                    "id": pinned_id,
                    "type": activity[:-1],
                    "text": text,
                    "timestamp": props.get("hs_timestamp")
                }

    return None

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
# ------------------------------------------------
# NEW: Get HubSpot Owner Name by Email
# ------------------------------------------------
async def get_sales_rep_name_by_email(email: str):
    # 1. Fetch all owners from HubSpot
    url = f"{BASE_URL}/crm/v3/owners"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
    logger.info(
            "HubSpot OWNERS response:\n%s",
            json.dumps(data, indent=2)
        )
    # 2. Search for the email (Case Insensitive)
    results = data.get("results", [])
    search_email = email.strip().lower()

    for owner in results:
        owner_email = owner.get("email", "").strip().lower()
        
        if owner_email == search_email:
            # Found a match! Combine First + Last Name
            first = owner.get("firstName", "")
            last = owner.get("lastName", "")
            full_name = f"{first} {last}".strip()
            
            logger.info(f"Mapped Email '{email}' -> Sales Rep '{full_name}'")
            return full_name
            
    logger.warning(f"No HubSpot Owner found for email: {email}")
    return None

    # ------------------------------------------------
# Search Contact by Email
# - Used to verify if a Wix user exists as a Contact in HubSpot
# - More efficient than fetching all contacts
# ------------------------------------------------
async def get_contact_by_email(email: str):
    url = f"{BASE_URL}/crm/v3/objects/contacts/search"
    
    payload = {
        "filterGroups": [
            {
                "filters": [
                    {
                        "propertyName": "email",
                        "operator": "EQ",
                        "value": email
                    }
                ]
            }
        ],
        "properties": ["email", "firstname", "lastname", "jobtitle","company"],
        "limit": 1
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        # Return the first match or None if no match found
        results = data.get("results", [])
        return results[0] if results else None
    
    # ------------------------------------------------
# Get Deals by Contact ID (Association Search)
# - Used for Wix Users who are matched to a HubSpot Contact
# - Filters Deals where the associated contact is {contact_id}
# ------------------------------------------------
async def get_deals_by_contact_id(contact_id: str):
    url = f"{BASE_URL}/crm/v3/objects/deals/search"

    payload = {
        "filterGroups": [
            {
                "filters": [
                    {
                        "propertyName": "associations.contact",
                        "operator": "EQ",
                        "value": contact_id
                    }
                ]
            }
        ],
        "properties": [
            "dealname",
            "dealstage",
            "project_address",
            "juridstiction",
            "dependency",
            "permit_number",
            "submittal_portal",
            "hs_lastmodifieddate",
            "description",
            "amount"
        ],
        "limit": 100
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])
    
async def get_sales_reps_under_pm(pm_email: str):

    contact = await get_contact_by_email(pm_email)

    if not contact:
        logger.warning(f"No contact found for {pm_email}")
        return []

    props = contact.get("properties", {})
    job_title = (props.get("jobtitle") or "").lower()

    # Validate role
    if "project manager" not in job_title:
        logger.warning(f"{pm_email} is not a Project Manager")
        return []

    pm_name = " ".join([
        props.get("firstname","").strip(),
        props.get("lastname","").strip()
    ]).strip()

    print("Resolved PM Name:", repr(pm_name))

    url = f"{BASE_URL}/crm/v3/objects/contacts/search"

    payload = {
        "filterGroups": [
            {
                "filters": [
                    {
                        "propertyName": "project_manager_email",
                        "operator": "EQ",
                        "value": pm_name   # ✅ FIX HERE
                    }
                ]
            }
        ],
        "properties": [
            "firstname",
            "lastname",
            "email",
            "jobtitle"
        ],
        "limit": 100
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        reps = response.json().get("results", [])

        # To display deal names, you must now iterate through these reps
        for rep in reps:
            rep_email = rep.get("properties", {}).get("email")
            # Call your existing search_deals_by_sales_rep using the rep's name
            rep_name = f"{rep['properties'].get('firstname','')} {rep['properties'].get('lastname','')}".strip()
            raw_deals = await search_deals_by_sales_rep(rep_name)
            rep["deals"] = [format_deal_for_pm_view(d) for d in raw_deals]

        return reps

def format_deal_for_pm_view(deal):
    """
    Filters and formats a HubSpot deal object to include only the properties
    requested for the Project Manager's Sales Rep view.
    """
    props = deal.get("properties", {})
    
    return {
        "id": deal.get("id"),
        "properties": {
            "createdate": props.get("createdate", "")[:10], # Truncates timestamp to YYYY-MM-DD
            "dealname": props.get("dealname"),
            "dealstage": props.get("dealstage"),
            "juridstiction": props.get("juridstiction"),
            "permit_number": props.get("permit_number"),
            "project_address": props.get("project_address"),
            "submittal_portal": props.get("submittal_portal")
        }
    }

# ------------------------------------------------
# NEW: General Manager (GM) / Company Level Logic
# ------------------------------------------------

async def get_gm_assigned_company(email: str):
    """
    Fetches the GM's contact record to find their assigned Company.
    Validates GM status by checking if this property exists.
    """
    contact = await get_contact_by_email(email)
    
    if not contact:
        logger.warning(f"No HubSpot contact found for GM email: {email}")
        return None

    props = contact.get("properties", {})
    
    # This property on the Contact record tells us which Company they manage.
    assigned_company = props.get("company") 
    
    if not assigned_company:
        logger.warning(f"Contact {email} has no assigned company value.")
        return None
        
    return assigned_company


async def search_deals_by_company(company_name: str):
    """
    Fetches ALL deals associated with a specific Company custom property.
    """
    url = f"{BASE_URL}/crm/v3/objects/deals/search"

    payload = {
        "filterGroups": [
            {
                "filters": [
                    {
                        # This is the custom property on the DEAL object.
                        "propertyName": "company", 
                        "operator": "EQ",
                        "value": company_name
                    }
                ]
            }
        ],
        "properties": [
            "dealname",
            "dealstage",
            "project_address",
            "juridstiction", # Keep typo if it exists in HubSpot
            "dependency",
            "permit_number",
            "sales_rep",     # CRITICAL: We need this to group by agent
            "hs_lastmodifieddate",
            "description"           
        ],
        "limit": 100
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json().get("results", [])


async def build_sales_rep_map():
    """
    Fetch all Contacts where jobtitle = 'Sales Rep'
    Build a name -> email map
    Cached in memory to avoid repeated API calls
    """
    global SALES_REP_CACHE

    if SALES_REP_CACHE:
        return SALES_REP_CACHE

    url = f"{BASE_URL}/crm/v3/objects/contacts/search"

    payload = {
        "filterGroups": [
            {
                "filters": [
                    {
                        "propertyName": "jobtitle",
                        "operator": "EQ",
                        "value": "Sales Rep"
                    }
                ]
            }
        ],
        "properties": ["firstname", "lastname", "email"],
        "limit": 100
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        reps = response.json().get("results", [])

    rep_map = {}
    for rep in reps:
        props = rep.get("properties", {})
        full_name = f"{props.get('firstname','')} {props.get('lastname','')}".strip()
        rep_map[full_name] = props.get("email")

    SALES_REP_CACHE = rep_map
    return rep_map
    
async def get_gm_dashboard_data(company_name: str):
    """
    Aggregates company deals into a structure that matches the 'List of Agents' UI.
    """
    # 1. Fetch raw deals
    deals = await search_deals_by_company(company_name)

    # 2. Build Sales Rep email map (single API call, cached)
    agent_email_map = await build_sales_rep_map()
    

    # 3. Initialize UI Structure
    dashboard_data = {
        "summary": {"intake":0,"pre_submittal": 0, "post_submittal": 0, "completed": 0},
        "agents": {},  # Dictionary for grouping: {"Ayudh": {count: 5, deals: []}}
        "permits": []  # Flat list for the table
    }

    # 4. Process & Group
    for deal in deals:
        props = deal.get("properties", {})
        print("props:",props)
        stage = normalize_permit_stage(props.get("dealstage"))
        
        # --- A. Summary Counts ---
        if "Intake" in stage:
            dashboard_data["summary"]["intake"] += 1
        elif any(x in stage for x in ["Fee Estimate", "Pre-Submittal"]):
            dashboard_data["summary"]["pre_submittal"] += 1
        elif "Submittal" in stage:
            dashboard_data["summary"]["post_submittal"] += 1
        elif any(x in stage for x in ["Approved", "Closed", "Issued"]):
            dashboard_data["summary"]["completed"] += 1

        # --- B. Group by Sales Agent ---
        agent_name = props.get("sales_rep") or "Unassigned"
        agent_email = agent_email_map.get(agent_name, "Unassigned")
        if agent_name not in dashboard_data["agents"]:
            dashboard_data["agents"][agent_name] = {
                "name": agent_name, 
                "email":agent_email,
                "count": 0,
                # We can store deal IDs here if the UI needs a "drill-down" later
                "deal_ids": [] 
            }
        print(dashboard_data["agents"])
        dashboard_data["agents"][agent_name]["count"] += 1
        dashboard_data["agents"][agent_name]["deal_ids"].append(deal.get("id"))

        # --- C. Table Data ---
        dashboard_data["permits"].append({
            "deal_id": deal.get("id"),
            "deal_name": props.get("dealname"),
            "stage": stage,
            "address": props.get("project_address"),
            "jurisdiction": props.get("juridstiction"),
            "sales_agent": agent_name  # Needed for the UI dropdown
        })

    # Convert agents dict to a clean list for JSON
    dashboard_data["agents"] = list(dashboard_data["agents"].values())
    
    return dashboard_data

async def get_latest_activity_for_deal(deal_id: str):

    url = f"{BASE_URL}/crm/v3/objects/notes/search"

    payload = {
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
        "sorts": [
            {
                "propertyName": "hs_createdate",
                "direction": "DESCENDING"
            }
        ],
        "limit": 1,
        "properties": ["hs_note_body", "hs_createdate"]
    }

    async with httpx.AsyncClient() as client:

        resp = await client.post(
            url,
            json=payload,
            headers=headers
        )

        resp.raise_for_status()

        data = resp.json()

        results = data.get("results", [])

        if not results:
            return None

        props = results[0]["properties"]

        return props.get("hs_note_body")

