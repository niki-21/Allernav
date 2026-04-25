import type { AllergyTag, DiningMode, ProfileSensitivity } from "./types";

export const ALLERGY_PROFILE_STORAGE_KEY = "allernav:selected-allergens";
export const PROFILE_PREFERENCES_STORAGE_KEY = "allernav:profile-preferences";

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
export const DEFAULT_SENSITIVITY: ProfileSensitivity = "careful";
export const DEFAULT_DINING_MODE: DiningMode = "grab_go";

export const SENSITIVITY_OPTIONS: Array<{
  value: ProfileSensitivity;
  label: string;
  description: string;
}> = [
  { value: "watchful", label: "Watchful", description: "Good for scouting options when evidence is still light." },
  { value: "careful", label: "Careful", description: "Balances speed with strong prompts to verify prep details." },
  { value: "strict", label: "Strict", description: "Best when you want to avoid low-evidence places entirely." },
];

export const DINING_MODE_OPTIONS: Array<{
  value: DiningMode;
  label: string;
  description: string;
}> = [
  { value: "grab_go", label: "Grab-and-go", description: "Fast options with simpler ordering paths." },
  { value: "sit_down", label: "Sit-down", description: "More time to ask questions and confirm modifications." },
  { value: "late_night", label: "Late night", description: "Useful when options are limited and kitchens are busy." },
  { value: "study_break", label: "Study break", description: "Quick cafe or casual food between classes." },
];

export function formatAllergenLabel(allergen: AllergyTag): string {
  return ALLERGEN_OPTIONS.find((option) => option.value === allergen)?.label ?? allergen;
}

export function formatSensitivityLabel(value: ProfileSensitivity): string {
  return SENSITIVITY_OPTIONS.find((option) => option.value === value)?.label ?? value;
}

export function formatDiningModeLabel(value: DiningMode): string {
  return DINING_MODE_OPTIONS.find((option) => option.value === value)?.label ?? value;
}
