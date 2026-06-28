# whitelist_ip.py (if in root)
import asyncio
import httpx
from app.services.cashfree_service import CashfreeService

async def main():
    # Get your current public IP
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.ipify.org")
        current_ip = response.text
    
    print(f"Your current public IP: {current_ip}")
    print(f"Whitelisting IP with Cashfree...")
    
    try:
        result = await CashfreeService.whitelist_ip(current_ip)
        print(f"✅ Success: {result}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())