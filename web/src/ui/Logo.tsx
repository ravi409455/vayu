/** The one Vayu lock-up: a red tile with the mark, and the name. The tile alone when space is tight. */
export function Logo({ big, markOnly }: { big?: boolean; markOnly?: boolean }) {
  return (
    <span className={`logo${big ? " big" : ""}`}>
      <span className="logo-mark" aria-hidden="true">
        V
      </span>
      {markOnly ? <span className="sr-only">Vayu</span> : <span className="logo-name">Vayu</span>}
    </span>
  );
}

/** Which server this is, shown next to the logo so nobody mistakes staging for production.
 *  Production (any other host) shows nothing. */
export function envName(host = typeof location === "undefined" ? "" : location.hostname): string | null {
  if (/^(localhost|127\.0\.0\.1|\[::1\])$/.test(host) || host.endsWith(".localhost") || host.endsWith(".test")) return "Local";
  if (/(^|[.-])(staging|stg|preview|dev|qa)([.-]|$)/.test(host)) return "Staging";
  return null;
}
