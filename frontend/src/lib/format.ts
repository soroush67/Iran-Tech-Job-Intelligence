const faNum = new Intl.NumberFormat("fa-IR");
const faDate = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { year: "numeric", month: "long", day: "numeric" });
const faDateTime = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
  year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
});

export const n = (v: number | null | undefined) => (v === null || v === undefined ? "—" : faNum.format(v));

export function date(v?: string | null) {
  return v ? faDate.format(new Date(v)) : "—";
}
export function dateTime(v?: string | null) {
  return v ? faDateTime.format(new Date(v)) : "—";
}

export function ago(v?: string | null) {
  if (!v) return "—";
  const s = (Date.now() - new Date(v).getTime()) / 1000;
  const rtf = new Intl.RelativeTimeFormat("fa", { numeric: "auto" });
  if (Math.abs(s) < 3600) return rtf.format(-Math.round(s / 60), "minute");
  if (Math.abs(s) < 86400) return rtf.format(-Math.round(s / 3600), "hour");
  return rtf.format(-Math.round(s / 86400), "day");
}

/** Monthly toman -> "۴۵ میلیون" */
export function toman(v?: number | null) {
  if (!v) return "—";
  if (v >= 1_000_000) return `${faNum.format(Math.round(v / 100_000) / 10)} میلیون`;
  return `${faNum.format(v)} تومان`;
}

export function salaryRange(min?: number | null, max?: number | null) {
  if (!min && !max) return "—";
  if (min && max && min !== max) return `${toman(min)} تا ${toman(max)}`;
  return toman(min || max);
}

export const pct = (v?: number | null) => (v === null || v === undefined ? "—" : `${faNum.format(Math.round(v * 100))}٪`);
