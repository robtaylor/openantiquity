import { LogIn } from "lucide-react";
import type { ReactNode } from "react";
import type { SignInProvider } from "../../api/meta.js";
import { noteSignInStarted } from "../drafts/store.js";
import { providerStartUrl } from "./api.js";

/**
 * One sign-in provider's button, in that provider's own style and wording:
 * Google's dark button, Apple's white button for dark backgrounds,
 * Microsoft's dark button, Facebook's blue button, and OpenStreetMap's mark.
 * Which providers are offered, and their names, come from /meta. A provider
 * this file doesn't know gets a plain button with the name /meta gives.
 *
 * The button is a link to the server's start route, so pressing it is a
 * full-page navigation, and `next` brings the person back to this view.
 * Pressing it notes that a sign-in started in this tab, so the drafts made
 * here before it are the person's when they come back (Decision 0022).
 */

interface Brand {
  /** The words the provider asks for. */
  text: (label: string) => string;
  mark: ReactNode;
}

const GOOGLE_MARK = (
  <svg viewBox="0 0 48 48" width="20" height="20" aria-hidden="true">
    <path
      fill="#EA4335"
      d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
    />
    <path
      fill="#4285F4"
      d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
    />
    <path
      fill="#FBBC05"
      d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
    />
    <path
      fill="#34A853"
      d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
    />
  </svg>
);

const APPLE_MARK = (
  <svg viewBox="0 0 814 1000" width="16" height="20" aria-hidden="true">
    <path
      fill="currentColor"
      d="M788.1 340.9c-5.8 4.5-108.2 62.2-108.2 190.5 0 148.4 130.3 200.9 134.2 202.2-.6 3.2-20.7 71.9-68.7 141.9-42.8 61.6-87.5 123.1-155.5 123.1s-85.5-39.5-164-39.5c-76.5 0-103.7 40.8-165.9 40.8s-105.6-57-155.5-127C46.7 790.7 0 663 0 541.8c0-194.4 126.4-297.5 250.8-297.5 66.1 0 121.2 43.4 162.7 43.4 39.5 0 101.1-46 176.3-46 28.5 0 130.9 2.6 198.3 99.2zm-234-181.5c31.1-36.9 53.1-88.1 53.1-139.3 0-7.1-.6-14.3-1.9-20.1-50.6 1.9-110.8 33.7-147.1 75.8-28.5 32.4-55.1 83.6-55.1 135.5 0 7.8 1.3 15.6 1.9 18.1 3.2.6 8.4 1.3 13.6 1.3 45.4 0 102.5-30.4 135.5-71.3z"
    />
  </svg>
);

const MICROSOFT_MARK = (
  <svg viewBox="0 0 21 21" width="21" height="21" aria-hidden="true">
    <rect x="1" y="1" width="9" height="9" fill="#F25022" />
    <rect x="11" y="1" width="9" height="9" fill="#7FBA00" />
    <rect x="1" y="11" width="9" height="9" fill="#00A4EF" />
    <rect x="11" y="11" width="9" height="9" fill="#FFB900" />
  </svg>
);

const FACEBOOK_MARK = (
  <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
    <circle cx="12" cy="12" r="12" fill="#FFFFFF" />
    <path
      fill="#1877F2"
      d="M16.67 15.47l.53-3.47h-3.33V9.75c0-.95.47-1.88 1.95-1.88h1.51V4.92s-1.37-.23-2.69-.23c-2.74 0-4.53 1.66-4.53 4.67V12H7.08v3.47h3.05v8.39a12.1 12.1 0 0 0 3.74 0v-8.39h2.8z"
    />
  </svg>
);

/** A magnifying glass over a scrap of map: the OpenStreetMap mark, simplified. */
const OSM_MARK = (
  <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
    <circle cx="10" cy="10" r="8" fill="#F2EFE9" stroke="#7EBC6F" strokeWidth="2" />
    <path d="M4.5 12.5c2-1 3.5.5 5.5-.5s2.5-3 5.5-3" stroke="#7EBC6F" strokeWidth="1.6" fill="none" />
    <path d="M7 5.5l2 9" stroke="#9A8F7A" strokeWidth="1.2" />
    <path d="M15.8 15.8l5.7 5.7" stroke="#7EBC6F" strokeWidth="3" strokeLinecap="round" />
  </svg>
);

const BRANDS: Readonly<Record<string, Brand>> = {
  google: { text: (label) => `Continue with ${label}`, mark: GOOGLE_MARK },
  apple: { text: (label) => `Continue with ${label}`, mark: APPLE_MARK },
  microsoft: { text: (label) => `Sign in with ${label}`, mark: MICROSOFT_MARK },
  facebook: { text: (label) => `Continue with ${label}`, mark: FACEBOOK_MARK },
  osm: { text: (label) => `Sign in with ${label}`, mark: OSM_MARK },
};

export function ProviderButton({ provider, next }: { provider: SignInProvider; next: string }) {
  const brand = Object.hasOwn(BRANDS, provider.id) ? BRANDS[provider.id] : undefined;
  const style = brand ? provider.id : "other";
  return (
    <a
      className={`fc-provider fc-provider--${style}`}
      href={providerStartUrl(provider.id, next)}
      onClick={() => noteSignInStarted("provider")}
    >
      <span className="fc-provider__mark">{brand ? brand.mark : <LogIn size={18} aria-hidden />}</span>
      <span className="fc-provider__text">{brand ? brand.text(provider.label) : `Sign in with ${provider.label}`}</span>
    </a>
  );
}
