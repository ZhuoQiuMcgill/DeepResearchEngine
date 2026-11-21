/** URL helpers shared by adapters and the citation check. */

const TRACKING_PARAMS = new Set(["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"]);

/** Remove provider tracking parameters, keeping everything else as written. */
export function cleanUrl(url: string): string {
  try {
    const u = new URL(url);
    let changed = false;
    for (const key of [...u.searchParams.keys()]) {
      if (TRACKING_PARAMS.has(key)) {
        u.searchParams.delete(key);
        changed = true;
      }
    }
    return changed ? u.toString() : url;
  } catch {
    return url;
  }
}

/** Characters whose escape changes how a path or query splits; they stay escaped (upper case) in keys. */
const STRUCTURAL = /[/?#%&=+]/g;

/**
 * Decode percent-escapes for comparison, so `%3A`, `%3a` and `:` give the same key.
 * `decodeURI` leaves reserved characters such as `:` escaped, which made one page
 * written two ways look like two pages. Escapes of structural characters stay
 * escaped, normalized to upper case; a malformed escape is kept as written.
 */
function decodeForKey(part: string): string {
  return part.replace(/(?:%[0-9a-f]{2})+/gi, (run) => {
    try {
      return decodeURIComponent(run).replace(STRUCTURAL, (c) => encodeURIComponent(c));
    } catch {
      return run.toUpperCase();
    }
  });
}

/** Comparison key: no scheme, no www, no trailing slash, no fragment, no tracking parameters. */
export function urlKey(url: string): string {
  try {
    const u = new URL(cleanUrl(url));
    const host = u.hostname.toLowerCase().replace(/^www\./, "");
    const path = decodeForKey(u.pathname).replace(/\/+$/, "");
    return `${host}${path}${decodeForKey(u.search)}`;
  } catch {
    return url.trim().replace(/\/+$/, "");
  }
}

/** Looser key without the query string, for "same page" checks across tracking or session parameters. */
export function pageKey(url: string): string {
  return urlKey(url).replace(/\?.*$/, "");
}

/** Candidate URL runs; parentheses are allowed so URLs like `.../Design-(EBD)-Zeng/` survive. */
const URL_RUN = /https?:\/\/[^\s<>"'\]`]+/g;

/**
 * Split a matched run into the URL and trailing text that is not part of it:
 * closing parentheses beyond the URL's own balance (Markdown link or prose
 * brackets) and trailing sentence punctuation.
 */
function splitTail(run: string): [string, string] {
  let url = run;
  for (;;) {
    const trimmed = url.replace(/[.,;:!?*_]+$/, "");
    if (trimmed !== url) {
      url = trimmed;
      continue;
    }
    if (url.endsWith(")") && (url.match(/\)/g)?.length ?? 0) > (url.match(/\(/g)?.length ?? 0)) {
      url = url.slice(0, -1);
      continue;
    }
    break;
  }
  return [url, run.slice(url.length)];
}

/** Remove `?utm_source=...` style tracking from every URL in a Markdown text. */
export function cleanUrlsInText(text: string): string {
  return text.replace(URL_RUN, (run) => {
    const [url, tail] = splitTail(run);
    return cleanUrl(url) + tail;
  });
}

/** URLs referenced in Markdown text: link targets and bare URLs. */
export function extractUrls(text: string): string[] {
  const found = new Set<string>();
  for (const m of text.matchAll(URL_RUN)) {
    const [url] = splitTail(m[0]);
    if (url.length > "https://".length) found.add(url);
  }
  return [...found];
}
