/**
 * The phone app's language setting. English is the source text; other languages come from the
 * gateway's /translate endpoint (Cloud Translation), batched and cached per language in this
 * browser. Until a translation arrives, or if translation is unavailable, English is shown.
 *
 * t("Pay {0} to {1}", [amount, upiId]): names, amounts and UPI IDs go in as {0}-style
 * placeholders, so they are never translated.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { useRole } from "../role";

export const LANGUAGES: { code: string; native: string; english: string }[] = [
  { code: "en", native: "English", english: "English" },
  { code: "hi", native: "हिन्दी", english: "Hindi" },
  { code: "bn", native: "বাংলা", english: "Bengali" },
  { code: "te", native: "తెలుగు", english: "Telugu" },
  { code: "mr", native: "मराठी", english: "Marathi" },
  { code: "ta", native: "தமிழ்", english: "Tamil" },
  { code: "gu", native: "ગુજરાતી", english: "Gujarati" },
  { code: "kn", native: "ಕನ್ನಡ", english: "Kannada" },
  { code: "ml", native: "മലയാളം", english: "Malayalam" },
  { code: "pa", native: "ਪੰਜਾਬੀ", english: "Punjabi" },
  { code: "or", native: "ଓଡ଼ିଆ", english: "Odia" },
];

/** Reviewed Hindi for short labels that machine translation renders awkwardly. */
const REVIEWED: Record<string, Record<string, string>> = {
  hi: {
    "Proceed to pay": "भुगतान करें",
    "Scan QR": "QR स्कैन करें",
    "Pay UPI ID": "UPI ID पर भुगतान",
    "Pay contact": "संपर्क को भुगतान",
    Messages: "संदेश",
    People: "लोग",
    "Paying {0}": "{0} को भुगतान",
    "Hi {0}": "नमस्ते {0}",
    "{0} to {1}": "{1} को {0}",
    "To {0}": "{0} को",
    "to {0}": "{0} को",
    "Pay {0} to {1}": "{1} को {0} का भुगतान करें",
    "{0} paid": "{0} का भुगतान हो गया",
    "Enter UPI PIN": "UPI PIN डालें",
    "Add a note": "नोट जोड़ें",
    Continue: "आगे बढ़ें",
    Done: "हो गया",
    "Back to home": "होम पर वापस जाएँ",
    Language: "भाषा",
  },
};

const STORAGE_LANG = "synthpay.language";
const storageKey = (lang: string) => `synthpay.translations.${lang}`;
const BATCH = 100;

function read<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Private mode or full storage: translations still work for this visit.
  }
}

function fill(text: string, vars: (string | number)[]): string {
  return text.replace(/\{(\d+)\}/g, (m, i) => (vars[Number(i)] ?? m).toString());
}

interface LanguageValue {
  lang: string;
  setLang: (code: string) => void;
  t: (text: string, vars?: (string | number)[]) => string;
  /** True while some text on screen is still being translated. */
  translating: boolean;
  /** True if the last translation request failed (English is shown instead). */
  unavailable: boolean;
}

const LanguageContext = createContext<LanguageValue | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const { api } = useRole();
  const [lang, setLangState] = useState(() => {
    const saved = read<string>(STORAGE_LANG, "en");
    return LANGUAGES.some((l) => l.code === saved) ? saved : "en";
  });
  const [dict, setDict] = useState<Record<string, string>>(() =>
    lang === "en" ? {} : read(storageKey(lang), {}),
  );
  const [pending, setPending] = useState(0);
  const [unavailable, setUnavailable] = useState(false);
  const wanted = useRef(new Set<string>());
  const asked = useRef(new Set<string>());
  const [, setQueued] = useState(0);
  const flushScheduled = useRef(false);

  const setLang = useCallback((code: string) => {
    write(STORAGE_LANG, code);
    wanted.current.clear();
    asked.current.clear();
    setUnavailable(false);
    setDict(code === "en" ? {} : read(storageKey(code), {}));
    setLangState(code);
  }, []);

  const t = useCallback(
    (text: string, vars: (string | number)[] = []) => {
      if (lang === "en" || !text) return fill(text, vars);
      const known = REVIEWED[lang]?.[text] ?? dict[text];
      if (known === undefined && !asked.current.has(text) && !wanted.current.has(text)) {
        wanted.current.add(text);
        // New text can appear when only a child re-renders; re-render the provider (after this
        // render) so the effect below sends it.
        if (!flushScheduled.current) {
          flushScheduled.current = true;
          queueMicrotask(() => {
            flushScheduled.current = false;
            setQueued((n) => n + 1);
          });
        }
      }
      return fill(known ?? text, vars);
    },
    [lang, dict],
  );

  // Results for a language the customer has since switched away from are dropped.
  const current = useRef(lang);
  useEffect(() => {
    current.current = lang;
  }, [lang]);

  // After each render, translate whatever text appeared that isn't known yet. Each text is
  // asked for once per language; a failure leaves it in English (no retry loop). No deps on
  // purpose: t() queues text during render, and this drains the queue after the render.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (lang === "en" || wanted.current.size === 0) return;
    const texts = [...wanted.current];
    wanted.current.clear();
    texts.forEach((x) => asked.current.add(x));
    const forLang = lang;
    setPending((n) => n + 1);
    (async () => {
      try {
        const found: Record<string, string> = {};
        for (let i = 0; i < texts.length; i += BATCH) {
          const chunk = texts.slice(i, i + BATCH);
          const res = await api.translate(forLang, chunk);
          chunk.forEach((x, j) => (found[x] = res.translations[j] ?? x));
        }
        if (current.current !== forLang) return;
        setDict((prev) => {
          const next = { ...prev, ...found };
          write(storageKey(forLang), next);
          return next;
        });
        setUnavailable(false);
      } catch {
        if (current.current === forLang) setUnavailable(true);
      } finally {
        setPending((n) => n - 1);
      }
    })();
  });

  const translating = pending > 0;
  const value = useMemo(
    () => ({ lang, setLang, t, translating, unavailable }),
    [lang, setLang, t, translating, unavailable],
  );
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageValue {
  const value = useContext(LanguageContext);
  if (!value) throw new Error("useLanguage must be used inside <LanguageProvider>");
  return value;
}
