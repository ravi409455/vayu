import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { usePageTitle } from "./kit";

/** The last part of the breadcrumb (a booking ID, a form name). Detail pages set it; the top bar shows it. */
const Ctx = createContext<{ crumb: string; setCrumb: (s: string) => void }>({ crumb: "", setCrumb: () => {} });

export function CrumbProvider({ children }: { children: ReactNode }) {
  const [crumb, setCrumb] = useState("");
  return <Ctx.Provider value={{ crumb, setCrumb }}>{children}</Ctx.Provider>;
}

export const useCrumbText = () => useContext(Ctx).crumb;

/** Call from a detail page with what it is showing; cleared when the page goes away. The browser
 *  tab says it too ("DEMO-7 · Vayu"). */
export function useCrumb(label: string | undefined) {
  const { setCrumb } = useContext(Ctx);
  useEffect(() => {
    setCrumb(label ?? "");
    return () => setCrumb("");
  }, [label, setCrumb]);
  usePageTitle(label);
}
