import { Injectable } from "@angular/core";
import { AlertStatus, RuleDraft, SourceDraft, Workspace } from "./models";
@Injectable({ providedIn: "root" })
export class ApiService {
  private async request<T>(
    path: string,
    method = "GET",
    body?: unknown,
  ): Promise<T> {
    let response: Response;
    try {
      response = await fetch("/api" + path, {
        method,
        headers: { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(15000),
      });
    } catch {
      throw new Error(
        "Le serveur est injoignable. Vérifiez que le backend est lancé.",
      );
    }
    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error("Le serveur a renvoyé une réponse invalide.");
    }
    if (!response.ok) throw new Error(data.error || "La requête a échoué.");
    return data as T;
  }
  state(): Promise<Workspace> {
    return this.request("/state");
  }
  source(value: SourceDraft): Promise<Workspace> {
    return this.request("/sources", "POST", value);
  }
  rule(value: RuleDraft): Promise<Workspace> {
    return this.request("/rules", "POST", value);
  }
  toggle(
    type: "sources" | "rules",
    id: number,
    enabled: boolean,
  ): Promise<Workspace> {
    return this.request(`/${type}/${id}`, "PATCH", { enabled });
  }
  status(id: number, status: AlertStatus): Promise<Workspace> {
    return this.request(`/alerts/${id}`, "PATCH", { status });
  }
  scan(sourceId?: number): Promise<{ queued: number }> {
    return this.request("/scan", "POST", sourceId ? { sourceId } : {});
  }
}
