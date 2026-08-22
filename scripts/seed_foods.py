"""Idempotent seed script: `uv run seed-foods`. Populates the foods table with the same 51
starter foods the frontend's mock used (backend/data/seed_foods.json), skipping any name that
already exists so it's safe to re-run."""

import json
from pathlib import Path

import app.models  # noqa: F401  # ensures every table is registered on Base.metadata
from app.database import Base, SessionLocal, engine
from app.models.food import Food

SEED_FILE = Path(__file__).resolve().parent.parent / "data" / "seed_foods.json"


def main() -> None:
    Base.metadata.create_all(bind=engine)

    with SEED_FILE.open(encoding="utf-8") as f:
        raw_foods = json.load(f)

    db = SessionLocal()
    try:
        existing_names = {name for (name,) in db.query(Food.name).all()}
        created = 0
        for raw in raw_foods:
            if raw["name"] in existing_names:
                continue
            nutrients = raw["nutrients"]
            db.add(
                Food(
                    name=raw["name"],
                    aliases=raw.get("aliases", []),
                    category=raw.get("category", "custom"),
                    serving_label=raw["servingLabel"],
                    serving_grams=raw.get("servingGrams", 0),
                    calories=nutrients["calories"],
                    protein_g=nutrients.get("proteinG", 0),
                    carbs_g=nutrients.get("carbsG", 0),
                    fat_g=nutrients.get("fatG", 0),
                    fiber_g=nutrients.get("fiberG", 0),
                    sugar_g=nutrients.get("sugarG", 0),
                    sodium_mg=nutrients.get("sodiumMg", 0),
                )
            )
            created += 1
        db.commit()
        print(f"Seeded {created} new foods ({len(raw_foods) - created} already existed).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
