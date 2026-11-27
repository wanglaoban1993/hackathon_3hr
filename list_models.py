"""Check the Nebius key works and list available model IDs."""
from nebius_client import _get_api_key, get_client, get_model, mask

print(f"Using key {mask(_get_api_key())}, configured model: {get_model()}")
ids = sorted(m.id for m in get_client().models.list())
for i in ids:
    print(i)
print(f"\n{len(ids)} models. Configured model available: {get_model() in ids}")
