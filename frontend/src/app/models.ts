export type Severity = "low" | "medium" | "high" | "critical";
export type AlertStatus = "new" | "reviewing" | "resolved";
export interface Source {
  id: number;
  name: string;
  url: string;
  format: "rss" | "json" | "text";
  enabled: boolean;
  last_checked: string | null;
  last_status: "idle" | "scanning" | "ok" | "error";
  last_error: string;
  entry_count: number;
}
export interface Rule {
  id: number;
  label: string;
  kind: "keyword" | "domain" | "email";
  value: string;
  severity: Severity;
  enabled: boolean;
}
export interface Alert {
  id: number;
  source_id: number | null;
  rule_id: number | null;
  source_name: string;
  rule_label: string;
  title: string;
  excerpt: string;
  url: string;
  severity: Severity;
  signals: string[];
  status: AlertStatus;
  created_at: string;
  last_seen: string;
}
export interface Activity {
  id: number;
  kind: string;
  message: string;
  created_at: string;
}
export interface Workspace {
  sources: Source[];
  rules: Rule[];
  alerts: Alert[];
  activity: Activity[];
}
export interface SourceDraft {
  name: string;
  url: string;
  format: "rss" | "json" | "text";
}
export interface RuleDraft {
  label: string;
  kind: "keyword" | "domain" | "email";
  value: string;
  severity: Severity;
}
