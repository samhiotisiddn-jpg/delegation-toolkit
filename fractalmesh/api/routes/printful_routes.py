"""Printful print-on-demand routes."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/printful", tags=["printful"])


class OrderRequest(BaseModel):
    recipient: dict
    items: list[dict]


class ShippingRequest(BaseModel):
    recipient: dict
    items: list[dict]


@router.get("/store")
async def store_info():
    from integrations import printful
    try:
        return printful.get_store_info()
    except Exception as e:
        raise HTTPException(502, str(e))


@router.get("/products")
async def list_products():
    from integrations import printful
    try:
        return {"products": printful.list_products()}
    except Exception as e:
        raise HTTPException(502, str(e))


@router.get("/products/{product_id}")
async def get_product(product_id: int):
    from integrations import printful
    product = printful.get_product(product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    return product


@router.get("/catalog")
async def catalog(category_id: int | None = None):
    from integrations import printful
    return {"products": printful.list_catalog_products(category_id)}


@router.post("/orders")
async def create_order(req: OrderRequest):
    from integrations import printful
    result = printful.create_order(req.recipient, req.items)
    if "error" in result:
        raise HTTPException(502, result["error"])
    return result


@router.post("/shipping-rates")
async def shipping_rates(req: ShippingRequest):
    from integrations import printful
    return {"rates": printful.get_shipping_rates(req.recipient, req.items)}
