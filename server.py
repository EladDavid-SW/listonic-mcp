import os
import logging
import requests
import base64
from typing import Optional, List, Dict, Any
from mcp.server.fastmcp import FastMCP

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("listonic_mcp")

# Initialize FastMCP server
mcp = FastMCP("Listonic")

EMAIL = os.environ.get("LISTONIC_EMAIL")
PASSWORD = os.environ.get("LISTONIC_PASSWORD")

if not EMAIL or not PASSWORD:
    logger.error("Missing LISTONIC_EMAIL or LISTONIC_PASSWORD environment variables.")
    raise ValueError("LISTONIC_EMAIL and LISTONIC_PASSWORD environment variables must be set.")

# Hardcoded List ID as requested
LIST_ID = "209042810"

_access_token = None

def get_access_token() -> str:
    """Fetches or returns a cached Listonic access token."""
    global _access_token
    if _access_token:
        return _access_token

    client_id = "listonicv2"
    client_secret = "fjdfsoj9874jdfhjkh34jkhffdfff"
    auth_str = f"{client_id}:{client_secret}"
    b64_auth = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "clientauthorization": f"Bearer {b64_auth}"
    }
    
    data = {
        "username": EMAIL,
        "password": PASSWORD,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": "https://listonicv2api.jestemkucharzem.pl"
    }
    
    login_url = "https://api.listonic.com/api/loginextended?provider=password&autoMerge=1&autoDestruct=1"
    
    try:
        response = requests.post(login_url, headers=headers, data=data, timeout=10)
        response.raise_for_status()
        auth_data = response.json()
        _access_token = auth_data.get("access_token")
        if not _access_token:
            raise ValueError("Access token missing in response.")
        return _access_token
    except Exception as e:
        logger.error(f"Authentication failed: {str(e)}")
        raise

@mcp.resource("listonic://list")
def get_list_resource() -> str:
    """Read-only resource providing the primary grocery list and its items."""
    try:
        token = get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"https://api.listonic.com/api/lists/{LIST_ID}?includeShares=true"
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        lst = response.json()
        
        name = lst.get("Name", "Unnamed")
        items_count = len(lst.get("Items", []))
        
        output = [f"List: {name} (ID: {LIST_ID}) - {items_count} items"]
        for item in lst.get("Items", []):
            item_id = item.get("Id", "")
            checked = "[x]" if str(item.get("Checked")) == "1" else "[ ]"
            item_name = item.get("Name", "")
            amount = item.get("Amount", "")
            unit = item.get("Unit", "")
            output.append(f"  {checked} (ItemID: {item_id}) {amount} {unit} {item_name}".strip())
        
        return "\n".join(output)
    except Exception as e:
        logger.error(f"Failed to fetch list: {str(e)}")
        return f"Error fetching list: {str(e)}"

@mcp.tool()
def get_items() -> str:
    """
    Fetch your grocery list items from Listonic. Use this to find Item IDs before making edits.
    Returns a formatted string containing the list items.
    
    IMPORTANT CONTEXT FOR AI: 
    If an item is marked as checked/completed (e.g., '[x]'), it means the user most likely already HAS those items at home.
    If an item is unchecked (e.g., '[ ]'), it means the user needs to buy it.
    """
    return get_list_resource()

@mcp.tool()
def add_items(items: list[dict[str, Any]]) -> str:
    """
    Adds one or multiple new items to your grocery list.
    Args:
        items: A list of dictionaries. Each dictionary must have a 'name' (str). 
               Optionally include 'quantity' (str, default '1') and 'unit' (str, default '').
               Example: [{"name": "Milk", "quantity": "2", "unit": "liters"}, {"name": "Bread"}]
    """
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://api.listonic.com/api/lists/{LIST_ID}/items"
    
    results = []
    for item in items:
        item_name = item.get("name")
        if not item_name:
            results.append("Failed: Missing 'name'.")
            continue
            
        data = {
            "name": item_name,
            "quantity": item.get("quantity", "1"),
            "unit": item.get("unit", "")
        }
        
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            response.raise_for_status()
            logger.info(f"Added item '{item_name}'")
            results.append(f"Successfully added '{item_name}'.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to add '{item_name}': {str(e)}")
            results.append(f"Failed to add '{item_name}': {str(e)}")
            
    return "\n".join(results)

@mcp.tool()
def delete_items(item_ids: list[str]) -> str:
    """
    Deletes one or multiple items entirely from the grocery list.
    Args:
        item_ids: A list of specific item IDs (strings) to delete.
                  Example: ["123456", "789012"]
    """
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    results = []
    for item_id in item_ids:
        url = f"https://api.listonic.com/api/lists/{LIST_ID}/items/{item_id}"
        try:
            response = requests.delete(url, headers=headers, timeout=10)
            response.raise_for_status()
            logger.info(f"Deleted item {item_id}")
            results.append(f"Successfully deleted item {item_id}.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to delete {item_id}: {str(e)}")
            results.append(f"Failed to delete item {item_id}: {str(e)}")
            
    return "\n".join(results)

@mcp.tool()
def edit_items(items: list[dict[str, Any]]) -> str:
    """
    Edits one or multiple existing items. Most commonly used to check/uncheck items while shopping.
    Args:
        items: A list of dictionaries. Each must contain 'item_id'.
               Optional keys to update: 'is_checked' (bool), 'name' (str), 'quantity' (str).
               Example: [{"item_id": "123", "is_checked": True}, {"item_id": "456", "quantity": "3"}]
    """
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    results = []
    for item in items:
        item_id = item.get("item_id")
        if not item_id:
            results.append("Failed: Missing 'item_id'.")
            continue
            
        url = f"https://api.listonic.com/api/lists/{LIST_ID}/items/{item_id}"
        
        data = {}
        if "is_checked" in item:
            data["isChecked"] = item["is_checked"]
        if "name" in item:
            data["name"] = item["name"]
        if "quantity" in item:
            data["quantity"] = item["quantity"]
            
        if not data:
            results.append(f"No changes provided for item {item_id}.")
            continue
            
        try:
            response = requests.patch(url, headers=headers, json=data, timeout=10)
            response.raise_for_status()
            logger.info(f"Updated item {item_id} with {data}")
            results.append(f"Successfully updated item {item_id}.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to update {item_id}: {str(e)}")
            results.append(f"Failed to update item {item_id}: {str(e)}")
            
    return "\n".join(results)

if __name__ == "__main__":
    mcp.run()
