export async function modelRuntime(
  base: string,
  model: string | undefined,
  engine: string | undefined,
  key: string | undefined,
  signal: AbortSignal,
) {
  const headers = key ? { Authorization: `Bearer ${key}` } : undefined;
  if (engine === "ninfer") {
    const r = await fetch(`${base}/models`, { headers, signal });
    if (!r.ok) throw new Error("Model unavailable");
    const data = await r.json();
    const m = data.data?.find(
      (item: any) => item.id === model && item.owned_by === "ninfer",
    );
    if (!m) throw new Error("Expected model not found");
    return {
      context: m.max_model_len ?? null,
      slots: null,
      engine: "NInfer",
      modelFile: "Mixed NVFP4 / FP8",
      checked: Date.now(),
    };
  }
  const r = await fetch(`${base.replace(/\/v1$/, "")}/props`, {
    headers,
    signal,
  });
  if (!r.ok) throw new Error("Model unavailable");
  const p = await r.json();
  return {
    context: p.default_generation_settings?.n_ctx ?? null,
    slots: p.total_slots ?? null,
    engine: p.build_info ? `llama.cpp ${p.build_info}` : null,
    modelFile:
      typeof p.model_path === "string"
        ? p.model_path.split(/[\\/]/).pop()
        : null,
    checked: Date.now(),
  };
}
