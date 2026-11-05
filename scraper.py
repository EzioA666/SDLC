import asyncio

async def fetch_stockx(sku):
    # TODO: Implement StockX query logic
    # Graceful fallback: return empty dict on timeout
    pass

async def fetch_goat(sku):
    # TODO: Implement GOAT query logic
    # Graceful fallback: return empty dict on timeout
    pass

async def aggregate_prices(sku):
    # Concurrently execute scrapers to minimize user wait time
    results = await asyncio.gather(
        fetch_stockx(sku),
        fetch_goat(sku),
        return_exceptions=True
    )
    return results