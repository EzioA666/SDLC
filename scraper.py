import asyncio
import random

async def fetch_stockx(sku):
    await asyncio.sleep(1.2) 
    mock_price = random.randint(150, 300)
    return {"platform": "StockX", "price": f"${mock_price}.00", "url": f"https://stockx.com/search?s={sku}"}
    pass

async def fetch_goat(sku):
    await asyncio.sleep(0.9)
    mock_price = random.randint(145, 310)
    return {"platform": "GOAT", "price": f"${mock_price}.00", "url": f"https://www.goat.com/search?query={sku}"}
    pass

async def aggregate_prices(sku):
    # Concurrently execute scrapers to minimize user wait time
    results = results = await asyncio.gather(fetch_stockx(sku), fetch_goat(sku), return_exceptions=True)
    return [res for res in results if not isinstance(res, Exception)]