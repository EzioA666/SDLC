# ==============================================================================
# Module: scraper.py
# Author: Yunzhe Yu (Backend & DevOps)
# Description: Asynchronous multi-marketplace sneaker price scraper using 
#              curl_cffi TLS fingerprint spoofing. Concurrently queries GOAT, 
#              Stadium Goods, and Flight Club for live in-stock pricing and 
#              canonical product URLs.
# ==============================================================================

import asyncio
import json
import re
import urllib.parse
from curl_cffi.requests import AsyncSession

ALGOLIA_URL = "https://2fwotdvm2o-dsn.algolia.net/1/indexes/product_variants_v2/query"
ALGOLIA_HEADERS = {
    "x-algolia-api-key": "ac96de6fef0e02bb95d433d8d5c7038a",
    "x-algolia-application-id": "2FWOTDVM2O",
    "Content-Type": "application/json"
}

async def fetch_goat(sku):
    try:
        async with AsyncSession(impersonate="chrome") as session:
            # 1. Resolve canonical product slug, template ID, and SKU
            init_payload = {
                "params": f"query={urllib.parse.quote(sku)}&hitsPerPage=1&distinct=true"
            }
            init_res = await session.post(ALGOLIA_URL, headers=ALGOLIA_HEADERS, json=init_payload, timeout=8)
            if init_res.status_code != 200:
                return None

            hits = init_res.json().get("hits", [])
            if not hits:
                return None

            top_hit = hits[0]
            slug = top_hit.get("slug", "")
            template_id = top_hit.get("product_template_id", "")
            product_sku = top_hit.get("sku", "")
            product_name = top_hit.get("name", "")

            if not slug:
                return None

            product_url = f"https://www.goat.com/sneakers/{slug}"
            lowest_price = None
            lowest_size = None

            # 2. Query GOAT's live buy_bar_data endpoint (matches the live size bar on goat.com)
            for identifier in filter(None, [slug, str(template_id)]):
                bar_url = f"https://www.goat.com/web-api/v1/product_variants/buy_bar_data?productTemplateId={identifier}&countryCode=US"
                bar_res = await session.get(
                    bar_url,
                    headers={
                        "Accept": "application/json",
                        "Referer": product_url,
                        "Accept-Language": "en-US,en;q=0.9"
                    },
                    timeout=6
                )
                if bar_res.status_code == 200:
                    variants = bar_res.json()
                    if isinstance(variants, list):
                        for v in variants:
                            if (
                                v.get("shoeCondition") == "new_no_defects"
                                and v.get("boxCondition") == "good_condition"
                                and v.get("stockStatus") in ("multiple_in_stock", "single_in_stock")
                            ):
                                cents = v.get("lowestPriceCents", {}).get("amount", 0)
                                if cents and cents > 0:
                                    price_val = round(cents / 100, 2)
                                    if lowest_price is None or price_val < lowest_price:
                                        lowest_price = price_val
                                        lowest_size = v.get("sizeOption", {}).get("presentation")
                        if lowest_price is not None:
                            break

            # 3. Fallback: Parse live GOAT product page JSON-LD / embedded state if buy_bar_data is blocked
            if lowest_price is None:
                page_res = await session.get(
                    product_url,
                    headers={"Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-US,en;q=0.9"},
                    timeout=6
                )
                if page_res.status_code == 200:
                    ld_matches = re.findall(
                        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                        page_res.text,
                        re.DOTALL
                    )
                    for block in ld_matches:
                        try:
                            data = json.loads(block)
                            offers = data.get("offers", {})
                            low_p = offers.get("lowPrice") or offers.get("price")
                            if low_p and float(low_p) > 0:
                                lowest_price = round(float(low_p), 2)
                                break
                        except Exception:
                            continue

            # 4. Final Fallback: Algolia active in-stock variants only (must have instant_ship_lowest_price_cents)
            if lowest_price is None:
                facets = json.dumps([
                    [f"slug:{slug}"],
                    ["shoe_condition:new_no_defects"],
                    ["box_condition:good_condition"]
                ])
                var_payload = {
                    "params": f"query=&facetFilters={urllib.parse.quote(facets)}&hitsPerPage=100&distinct=false"
                }
                var_res = await session.post(ALGOLIA_URL, headers=ALGOLIA_HEADERS, json=var_payload, timeout=8)
                if var_res.status_code == 200:
                    for v in var_res.json().get("hits", []):
                        # Filter out stale/sold-out $125 records by requiring active instant/verified stock
                        instant_cents = v.get("instant_ship_lowest_price_cents")
                        cents = v.get("lowest_price_cents", 0)
                        if instant_cents and cents and cents > 0:
                            price_val = round(cents / 100, 2)
                            if lowest_price is None or price_val < lowest_price:
                                lowest_price = price_val
                                lowest_size = v.get("size")

            if lowest_price:
                return {
                    "platform": "GOAT",
                    "price": float(lowest_price),
                    "size": lowest_size,
                    "url": product_url,
                    "slug": slug,
                    "sku": product_sku,
                    "name": product_name
                }
    except Exception:
        pass
    return None


async def fetch_stadium_goods(sku, goat_data=None):
    """Fetches the exact Stadium Goods product page & filters strictly for in-stock sizes."""
    search_terms = []
    if goat_data and goat_data.get("sku"):
        raw_sku = goat_data["sku"].strip()
        search_terms.append(raw_sku)
        if " " in raw_sku:
            search_terms.append(raw_sku.replace(" ", "-"))
    search_terms.append(sku.strip())

    try:
        # Do NOT force US/USD cookies so the currency matches the user's local browser session
        async with AsyncSession(impersonate="chrome") as session:
            handle = None
            for term in search_terms:
                q = urllib.parse.quote(term)
                suggest_url = f"https://www.stadiumgoods.com/search/suggest.json?q={q}&resources[type]=product&resources[limit]=5"
                res = await session.get(suggest_url, headers={"Accept": "application/json"}, timeout=8)
                if res.status_code == 200:
                    products = (
                        res.json()
                        .get("resources", {})
                        .get("results", {})
                        .get("products", [])
                    )
                    for prod in products:
                        if prod.get("available", True) and prod.get("handle"):
                            handle = prod["handle"]
                            break
                if handle:
                    break

            if not handle:
                return None

            product_url = f"https://www.stadiumgoods.com/products/{handle}"

            # 1. Check rendered product HTML first (captures localized '$193 & up' display price directly)
            html_res = await session.get(
                product_url,
                headers={"Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-US,en;q=0.9"},
                timeout=8
            )
            if html_res.status_code == 200:
                # Match '$193 & up' or '$193 &amp; up' shown on the Stadium Goods product page
                up_match = re.search(r'\$\s*([\d,]+(?:\.\d{2})?)\s*(?:&amp;|&)\s*up', html_res.text, re.IGNORECASE)
                if up_match:
                    price_val = float(up_match.group(1).replace(",", ""))
                    if price_val > 0:
                        return {
                            "platform": "Stadium Goods",
                            "price": round(price_val, 2),
                            "size": None,
                            "url": product_url
                        }

            # 2. Fallback: Query Shopify product.js and filter strictly for available == True variants
            js_res = await session.get(f"{product_url}.js", headers={"Accept": "application/json"}, timeout=8)
            if js_res.status_code == 200:
                prod_data = js_res.json()
                lowest_price = None
                lowest_size = None
                for variant in prod_data.get("variants", []):
                    if variant.get("available") is True:
                        raw_p = variant.get("price", 0)
                        p_val = round(float(raw_p) / 100, 2) if float(raw_p) > 2500 else round(float(raw_p), 2)
                        if p_val > 0 and (lowest_price is None or p_val < lowest_price):
                            lowest_price = p_val
                            lowest_size = variant.get("title")

                if lowest_price:
                    return {
                        "platform": "Stadium Goods",
                        "price": lowest_price,
                        "size": lowest_size,
                        "url": product_url
                    }
    except Exception:
        pass
    return None


async def fetch_flight_club(sku, goat_data=None):
    """Resolves exact Flight Club product page and extracts live price from JSON-LD."""
    if not goat_data or not goat_data.get("slug"):
        return None

    slug = goat_data["slug"]
    fc_url = f"https://www.flightclub.com/{slug}"
    headers = {
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9"
    }

    try:
        async with AsyncSession(impersonate="chrome") as session:
            res = await session.get(fc_url, headers=headers, timeout=8)
            if res.status_code == 200:
                ld_matches = re.findall(
                    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                    res.text,
                    re.DOTALL
                )
                for block in ld_matches:
                    try:
                        data = json.loads(block)
                        offers = data.get("offers", {})
                        low_price = offers.get("lowPrice") or offers.get("price")
                        if low_price and float(low_price) > 0:
                            return {
                                "platform": "Flight Club",
                                "price": round(float(low_price), 2),
                                "size": None,
                                "url": fc_url
                            }
                    except Exception:
                        continue
    except Exception:
        pass
    return None


async def aggregate_prices(sku):
    goat_res = await fetch_goat(sku)

    sg_res, fc_res = await asyncio.gather(
        fetch_stadium_goods(sku, goat_res),
        fetch_flight_club(sku, goat_res),
        return_exceptions=True
    )

    results = []
    if isinstance(goat_res, dict) and goat_res.get("price"):
        results.append({
            "platform": "GOAT",
            "price": goat_res["price"],
            "size": goat_res.get("size"),
            "url": goat_res["url"]
        })

    for candidate in (sg_res, fc_res):
        if isinstance(candidate, dict) and candidate.get("price") and candidate.get("url"):
            results.append(candidate)

    results.sort(key=lambda x: x["price"])
    return results