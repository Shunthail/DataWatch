import { registerLocaleData } from "@angular/common";
import frenchLocale from "@angular/common/locales/fr";
import { LOCALE_ID } from "@angular/core";
import { bootstrapApplication } from "@angular/platform-browser";
import { AppComponent } from "./app/app.component";
registerLocaleData(frenchLocale);
bootstrapApplication(AppComponent, {
  providers: [{ provide: LOCALE_ID, useValue: "fr-FR" }],
}).catch(console.error);
