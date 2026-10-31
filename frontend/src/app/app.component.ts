import {
  Component,
  HostListener,
  OnDestroy,
  computed,
  inject,
  signal,
} from "@angular/core";
import { CommonModule } from "@angular/common";
import { FormsModule } from "@angular/forms";
import { ApiService } from "./api.service";
import {
  Alert,
  AlertStatus,
  RuleDraft,
  Severity,
  Source,
  SourceDraft,
  Workspace,
} from "./models";

type View = "alerts" | "sources" | "rules" | "history";
@Component({
  selector: "app-root",
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: "./app.component.html",
})
export class AppComponent implements OnDestroy {
  private readonly api = inject(ApiService);
  private readonly events = new EventSource("/api/events");
  readonly data = signal<Workspace>({
    sources: [],
    rules: [],
    alerts: [],
    activity: [],
  });
  readonly view = signal<View>("alerts");
  readonly connected = signal(false);
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly message = signal("");
  readonly search = signal("");
  readonly statusFilter = signal("all");
  readonly severityFilter = signal("all");
  readonly selectedId = signal<number | null>(null);
  readonly dialog = signal<"source" | "rule" | null>(null);
  readonly sourceDraft: SourceDraft = { name: "", url: "", format: "rss" };
  readonly ruleDraft: RuleDraft = {
    label: "",
    kind: "domain",
    value: "",
    severity: "medium",
  };
  readonly severityLabels: Record<Severity, string> = {
    critical: "Critique",
    high: "Élevée",
    medium: "Modérée",
    low: "Faible",
  };
  readonly statusLabels: Record<AlertStatus, string> = {
    new: "À examiner",
    reviewing: "En cours",
    resolved: "Clôturé",
  };
  readonly titles: Record<View, string> = {
    alerts: "Signalements",
    sources: "Sources publiques",
    rules: "Règles de veille",
    history: "Journal d’activité",
  };
  readonly descriptions: Record<View, string> = {
    alerts:
      "Les publications qui correspondent à votre périmètre de surveillance.",
    sources: "Les flux consultés automatiquement, toutes les cinq minutes.",
    rules:
      "Les expressions, domaines et adresses à rechercher dans vos sources.",
    history:
      "Le suivi des collectes, des règles et des décisions de traitement.",
  };
  readonly activeSources = computed(() =>
    this.data().sources.filter((source) => source.enabled),
  );
  readonly activeRules = computed(() =>
    this.data().rules.filter((rule) => rule.enabled),
  );
  readonly selected = computed(
    () =>
      this.data().alerts.find((alert) => alert.id === this.selectedId()) ||
      null,
  );
  readonly filteredAlerts = computed(() =>
    this.data().alerts.filter(
      (alert) =>
        (this.statusFilter() === "all" ||
          alert.status === this.statusFilter()) &&
        (this.severityFilter() === "all" ||
          alert.severity === this.severityFilter()) &&
        `${alert.title} ${alert.excerpt} ${alert.source_name} ${alert.rule_label}`
          .toLowerCase()
          .includes(this.search().toLowerCase()),
    ),
  );
  readonly filteredSources = computed(() =>
    this.data().sources.filter((source) =>
      `${source.name} ${source.url}`
        .toLowerCase()
        .includes(this.search().toLowerCase()),
    ),
  );
  readonly filteredRules = computed(() =>
    this.data().rules.filter((rule) =>
      `${rule.label} ${rule.value}`
        .toLowerCase()
        .includes(this.search().toLowerCase()),
    ),
  );
  readonly filteredActivity = computed(() =>
    this.data().activity.filter((item) =>
      item.message.toLowerCase().includes(this.search().toLowerCase()),
    ),
  );
  readonly lastCollection = computed(() =>
    this.data()
      .sources.map((source) => source.last_checked)
      .filter((date): date is string => date !== null)
      .sort()
      .at(-1),
  );

  constructor() {
    void this.refresh();
    this.events.onopen = () => this.connected.set(true);
    this.events.onerror = () => this.connected.set(false);
    this.events.addEventListener("update", () => void this.refresh());
  }
  ngOnDestroy(): void {
    this.events.close();
  }
  @HostListener("document:keydown.escape") closeDialog(): void {
    if (!this.busy()) {
      this.dialog.set(null);
      this.selectedId.set(null);
    }
  }
  navigate(view: View): void {
    this.view.set(view);
    this.search.set("");
    this.selectedId.set(null);
    this.statusFilter.set("all");
    this.severityFilter.set("all");
  }
  filterByRule(label: string): void {
    this.navigate("alerts");
    this.search.set(label);
  }
  async refresh(): Promise<void> {
    try {
      this.data.set(await this.api.state());
    } catch (error) {
      this.fail(error);
    } finally {
      this.loading.set(false);
    }
  }
  private fail(error: unknown): void {
    this.message.set(
      error instanceof Error ? error.message : "Une erreur est survenue.",
    );
  }
  openDialog(type: "source" | "rule"): void {
    this.message.set("");
    this.dialog.set(type);
  }
  async save(): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true);
    this.message.set("");
    try {
      this.data.set(
        this.dialog() === "source"
          ? await this.api.source(this.sourceDraft)
          : await this.api.rule(this.ruleDraft),
      );
      if (this.dialog() === "source")
        Object.assign(this.sourceDraft, { name: "", url: "", format: "rss" });
      else
        Object.assign(this.ruleDraft, {
          label: "",
          kind: "domain",
          value: "",
          severity: "medium",
        });
      this.dialog.set(null);
    } catch (error) {
      this.fail(error);
    } finally {
      this.busy.set(false);
    }
  }
  async toggle(
    type: "sources" | "rules",
    id: number,
    enabled: boolean,
  ): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true);
    this.message.set("");
    try {
      this.data.set(await this.api.toggle(type, id, enabled));
    } catch (error) {
      this.fail(error);
    } finally {
      this.busy.set(false);
    }
  }
  async changeStatus(alert: Alert, status: AlertStatus): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true);
    this.message.set("");
    try {
      this.data.set(await this.api.status(alert.id, status));
    } catch (error) {
      this.fail(error);
    } finally {
      this.busy.set(false);
    }
  }
  async scan(source?: Source): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true);
    this.message.set("");
    try {
      const result = await this.api.scan(source?.id);
      this.message.set(
        result.queued
          ? `${result.queued} source(s) ajoutée(s) à la collecte.`
          : "Les sources sont déjà en cours de collecte.",
      );
      await this.refresh();
    } catch (error) {
      this.fail(error);
    } finally {
      this.busy.set(false);
    }
  }
  sourceStatus(source: Source): string {
    if (!source.enabled) return "En pause";
    return {
      idle: "En attente",
      scanning: "Collecte en cours",
      ok: "À jour",
      error: "Erreur de collecte",
    }[source.last_status];
  }
  domain(url: string): string {
    try {
      return new URL(url).host;
    } catch {
      return url;
    }
  }
  exportData(): void {
    const payload =
      this.view() === "history"
        ? this.filteredActivity()
        : this.filteredAlerts();
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json",
      }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `datawatch-${this.view()}-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
