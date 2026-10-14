export const CATEGORIES = ["devops", "sre", "python", "ai_ml", "mlops_data"] as const;
export type Category = (typeof CATEGORIES)[number];

export const CATEGORY_LABEL: Record<string, string> = {
  devops: "DevOps / Platform",
  sre: "SRE / Reliability",
  python: "Python Development",
  ai_ml: "AI / Machine Learning",
  mlops_data: "MLOps / Data",
};

/** Fixed category -> chart slot (never by rank). */
export const CATEGORY_COLOR: Record<string, string> = {
  devops: "var(--series-1)",
  sre: "var(--series-2)",
  python: "var(--series-3)",
  ai_ml: "var(--series-4)",
  mlops_data: "var(--series-5)",
};

export const WORK_MODE: Record<string, string> = { onsite: "حضوری", hybrid: "هیبریدی", remote: "دورکاری", unknown: "نامشخص" };
export const SENIORITY: Record<string, string> = {
  junior: "Junior", mid: "Mid-Level", senior: "Senior", staff: "Staff", principal: "Principal", unknown: "نامشخص",
};
export const EMPLOYMENT: Record<string, string> = {
  full_time: "تمام‌وقت", part_time: "پاره‌وقت", contract: "قراردادی/پروژه‌ای", internship: "کارآموزی",
};
export const SALARY_STATUS: Record<string, string> = { reported: "اعلام‌شده", estimated: "تخمینی", unknown: "نامشخص" };
export const JOB_STATUS: Record<string, string> = { active: "فعال", expired: "منقضی", unknown: "نامشخص" };
export const EVENT: Record<string, string> = {
  NEW_JOB: "آگهی جدید",
  SALARY_CHANGED: "تغییر حقوق",
  DESCRIPTION_CHANGED: "تغییر شرح شغل",
  REQUIREMENTS_CHANGED: "تغییر شرایط/مهارت‌ها",
  WORK_MODE_CHANGED: "تغییر شیوه همکاری",
  JOB_EXPIRED: "منقضی شد",
  JOB_REOPENED: "دوباره فعال شد",
};
export const SOURCE_STATUS: Record<string, { label: string; tone: "good" | "warning" | "critical" | "secondary" }> = {
  healthy: { label: "Healthy - سالم", tone: "good" },
  degraded: { label: "Degraded - ناقص", tone: "warning" },
  blocked: { label: "Blocked - مسدود", tone: "critical" },
  disabled: { label: "Disabled - غیرفعال", tone: "secondary" },
  unknown: { label: "هنوز اجرا نشده", tone: "secondary" },
};
export const TRANSPARENCY: Record<string, string> = { high: "بالا", medium: "متوسط", low: "پایین", unknown: "Unknown - داده ناکافی" };
export const SOURCE_NAME: Record<string, string> = { jobinja: "جابینجا", jobvision: "جاب‌ویژن" };
