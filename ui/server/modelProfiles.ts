export type ModelProfileId = "local" | "api";

type ModelProfile = {
  id: ModelProfileId;
  base: string;
  model: string;
  key: string | undefined;
  engine?: string;
  thinkingOff?: boolean;
  minimumContext?: number;
};

export function isModelProfileId(value: unknown): value is ModelProfileId {
  return value === "local" || value === "api";
}

function baseUrl(value: string | undefined): URL | undefined {
  if (!value) return;
  try {
    const url = new URL(value);
    if (
      ["http:", "https:"].includes(url.protocol) &&
      !url.username &&
      !url.password &&
      !url.search &&
      !url.hash
    ) {
      return url;
    }
  } catch {
    // A malformed endpoint must never be available for requests.
  }
}

export function loadModelProfiles(env: Record<string, string>) {
  const profiles: Partial<Record<ModelProfileId, ModelProfile>> = {};
  const legacy = baseUrl(env.PLANNER_BASE_URL);
  const legacyModel = env.PLANNER_MODEL?.trim();
  const minimumContext = Number(env.PLANNER_MIN_CONTEXT || 0);
  let defaultProfile: ModelProfileId | null = null;

  if (legacy && legacyModel) {
    const isLocal =
      ["localhost", "[::1]"].includes(legacy.hostname) ||
      /^127(?:\.\d{1,3}){3}$/.test(legacy.hostname) ||
      Boolean(env.PLANNER_ENGINE) ||
      minimumContext > 0;
    const id = isLocal ? "local" : "api";
    defaultProfile = id;
    profiles[id] = {
      id,
      base: legacy.href.replace(/\/+$/, ""),
      model: legacyModel,
      key: env.PLANNER_API_KEY,
      ...(isLocal && {
        engine: env.PLANNER_ENGINE,
        thinkingOff: env.PLANNER_ENABLE_THINKING === "false",
        minimumContext: Number.isFinite(minimumContext) ? minimumContext : 0,
      }),
    };
  }

  const remote = baseUrl(env.PLANNER_REMOTE_BASE_URL);
  const remoteModel = env.PLANNER_REMOTE_MODEL?.trim();
  if (remote && remoteModel) {
    profiles.api = {
      id: "api",
      base: remote.href.replace(/\/+$/, ""),
      model: remoteModel,
      key: env.PLANNER_REMOTE_API_KEY,
    };
    defaultProfile ??= "api";
  }

  const available = (["local", "api"] as const).flatMap((id) => {
    const profile = profiles[id];
    return profile ? [{ id, model: profile.model }] : [];
  });
  return { profiles, available, defaultProfile };
}
