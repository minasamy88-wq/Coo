"""Pre-populate database with known Ontario rental properties and provider mappings."""

from .database import create_property, get_all_properties, get_property_by_name, init_db
from .models import PropertyModel

# Known properties with their city and provider mappings.
# Providers listed here will be used to auto-match uploaded bills.
PROPERTIES = [
    # Sarnia / Bluewater Power area
    {"name": "892 Wellington", "city": "Sarnia", "gas": "Enbridge", "hydro_water": "Bluewater Power"},
    {"name": "104 Dundas", "city": "Sarnia", "gas": "Enbridge", "hydro_water": "Bluewater Power"},
    {"name": "222 Maxwell", "city": "Sarnia", "gas": "Enbridge", "hydro_water": "Bluewater Power"},
    {"name": "355 Indian Rd", "city": "Sarnia", "gas": "Enbridge", "hydro_water": "Bluewater Power"},
    {"name": "357 Indian", "city": "Sarnia", "gas": "Enbridge", "hydro_water": "Bluewater Power"},
    # Chatham-Kent / Entegrus area
    {"name": "89 Sheldon", "city": "Chatham-Kent", "gas": "Enbridge", "hydro_water": "Entegrus"},
    {"name": "St Anthony", "city": "Chatham-Kent", "gas": "Enbridge", "hydro_water": "Entegrus"},
    # Windsor / Enwin area
    {"name": "214 Curry", "city": "Windsor", "gas": "Enbridge", "hydro_water": "Enwin"},
    {"name": "1338 Ouellette", "city": "Windsor", "gas": "Enbridge", "hydro_water": "Enwin"},
    {"name": "Moy", "city": "Windsor", "gas": "Enbridge", "hydro_water": "Enwin"},
    {"name": "1398 Ouellette", "city": "Windsor", "gas": "Enbridge", "hydro_water": None},
    # London / London Hydro area
    {"name": "421 Chester", "city": "London", "gas": "Enbridge", "hydro_water": "London Hydro"},
    {"name": "321 Chester", "city": "London", "gas": "Enbridge", "hydro_water": "London Hydro"},
    # Guelph / Guelph Hydro area
    {"name": "79 Macdonell", "city": "Guelph", "gas": None, "hydro_water": "Guelph Hydro"},
    {"name": "90 Carden", "city": "Guelph", "gas": "Enbridge", "hydro_water": "Guelph Hydro"},
    {"name": "81 Macdonell", "city": "Guelph", "gas": None, "hydro_water": "Guelph Hydro"},
    # Rural / Hydro One area
    {"name": "Southriver", "city": "Southriver", "gas": "Enbridge", "hydro_water": "Hydro One"},
    {"name": "Lyndoch", "city": "Lyndoch", "gas": "Enbridge", "hydro_water": "Hydro One"},
    # Properties with only Enbridge gas confirmed (hydro/water provider TBD)
    {"name": "512 English", "city": None, "gas": "Enbridge", "hydro_water": None},
    {"name": "Blenheim", "city": None, "gas": "Enbridge", "hydro_water": None},
    {"name": "Cypress", "city": None, "gas": "Enbridge", "hydro_water": None},
    {"name": "16 Ellis", "city": None, "gas": "Enbridge", "hydro_water": None},
    {"name": "1741 University", "city": None, "gas": "Enbridge", "hydro_water": None},
    {"name": "321 Hill", "city": None, "gas": "Enbridge", "hydro_water": None},
]

# Map of property name -> expected providers, used for auto-matching bills
PROPERTY_PROVIDER_MAP: dict[str, dict[str, str | None]] = {
    p["name"]: {"gas": p["gas"], "hydro_water": p["hydro_water"]}
    for p in PROPERTIES
}


def seed():
    """Seed the database with known properties. Skips properties that already exist."""
    init_db()
    existing = {p.name for p in get_all_properties()}
    created = 0

    for prop_data in PROPERTIES:
        if prop_data["name"] in existing:
            continue
        prop = PropertyModel(
            name=prop_data["name"],
            city=prop_data["city"],
            province="ON",
            notes=_build_provider_notes(prop_data),
        )
        create_property(prop)
        created += 1

    return created


def _build_provider_notes(prop_data: dict) -> str:
    """Build a notes string summarizing known providers for a property."""
    parts = []
    if prop_data.get("gas"):
        parts.append(f"Gas: {prop_data['gas']}")
    if prop_data.get("hydro_water"):
        parts.append(f"Hydro+Water: {prop_data['hydro_water']}")
    return " | ".join(parts) if parts else ""


def get_expected_provider(property_name: str, utility_type: str) -> str | None:
    """Look up the expected provider for a property and utility type."""
    mapping = PROPERTY_PROVIDER_MAP.get(property_name)
    if not mapping:
        return None
    if utility_type == "gas":
        return mapping.get("gas")
    if utility_type in ("hydro", "water", "sewer"):
        return mapping.get("hydro_water")
    return None


if __name__ == "__main__":
    count = seed()
    print(f"Seeded {count} properties.")
