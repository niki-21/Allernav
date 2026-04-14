import type { AllergyTag } from "./types";

export const ALLERGY_PROFILE_STORAGE_KEY = "allernav:selected-allergens";

export const ALLERGEN_OPTIONS: Array<{
  value: AllergyTag;
  label: string;
  shortLabel: string;
}> = [
  { value: "peanut", label: "Peanut", shortLabel: "Peanut" },
  { value: "tree_nut", label: "Tree Nut", shortLabel: "Tree nuts" },
  { value: "dairy", label: "Dairy", shortLabel: "Dairy" },
  { value: "egg", label: "Egg", shortLabel: "Egg" },
  { value: "shellfish", label: "Shellfish", shortLabel: "Shellfish" },
  { value: "fish", label: "Fish", shortLabel: "Fish" },
  { value: "soy", label: "Soy", shortLabel: "Soy" },
  { value: "sesame", label: "Sesame", shortLabel: "Sesame" },
  { value: "wheat_gluten", label: "Wheat / Gluten", shortLabel: "Gluten" },
];

export const DEFAULT_ALLERGENS: AllergyTag[] = ["peanut"];

export function formatAllergenLabel(allergen: AllergyTag): string {
  return ALLERGEN_OPTIONS.find((option) => option.value === allergen)?.label ?? allergen;
}

