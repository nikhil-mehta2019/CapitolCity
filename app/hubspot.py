import httpx
from .config import HUBSPOT_TOKEN, BASE_URL

headers = {
    "Authorization": f"Bearer {HUBSPOT_TOKEN}",
    "Content-Type": "application/json"
}

async def get_deal(deal_id: str):
    url = f"{BASE_URL}/crm/v3/objects/deals/{deal_id}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


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
            "permit_stage",
            "jurisdiction",
            "project_address",
            "dependency"
        ],
        "limit": 100
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
