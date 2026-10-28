import { en } from "./en";
import { km } from "./km";

export type Locale = "km" | "en";
export type LocalizedRollType = { code: string; name_km: string; name_en: string };
export type LocalizedRollTypePayload = {
  roll_type_code?: string | null;
  roll_type_name?: string | null;
  roll_type_name_km?: string | null;
  roll_type_name_en?: string | null;
};

const dictionaries = { km, en };
const activeLocale: Locale = "km";

export function translate(key: keyof typeof km.labels): string {
  return dictionaries[activeLocale].labels[key];
}

export function rollTypeLabel(rollType: LocalizedRollType): string {
  const displayName = activeLocale === "km" ? rollType.name_km : rollType.name_en;
  const fallback = activeLocale === "km"
    ? km.rollTypes[rollType.code as keyof typeof km.rollTypes]
    : en.rollTypes[rollType.code as keyof typeof en.rollTypes];
  return displayName || fallback || rollType.code;
}

export function rollTypeText(rollType: LocalizedRollTypePayload): string {
  const code = rollType.roll_type_code ?? "";
  const localized = activeLocale === "km"
    ? rollType.roll_type_name_km ?? rollType.roll_type_name
    : rollType.roll_type_name_en;
  const fallback = activeLocale === "km"
    ? km.rollTypes[code as keyof typeof km.rollTypes]
    : en.rollTypes[code as keyof typeof en.rollTypes];
  return localized || fallback || code || "—";
}
