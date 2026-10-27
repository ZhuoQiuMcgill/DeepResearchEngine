/**
 * One structured-call helper for the strategy's judgment roles (design section 5.3):
 *
 * 1. Bind one unforced submit tool whose schema carries types, enums and required
 *    fields only. Unforced, so Haiku keeps its thinking; not strict, so a large
 *    schema cannot hit Anthropic's grammar limits (Lab 3, section 2.3).
 * 2. Validate the tool's arguments with the API schema.
 * 3. Apply the role's rule checks.
 * 4. On any error, retry once with the previous reply and the numbered errors.
 * 5. If the retry fails too, return the role's fallback from the last valid reply.
 *
 * The request analysis keeps its own loop in request/ (fixed and agent modes);
 * this helper serves the conflict checker and the round analyst.
 */
import { HumanMessage, SystemMessage, type AIMessage, type BaseMessage } from "@langchain/core/messages";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { Runnable } from "@langchain/core/runnables";
import type { z } from "zod";
import { apiJsonSchema, type FunctionTool, type Issue } from "./request/index.js";
import { textOf, usageOf } from "./request/trace.js";
import type { CallRecord } from "./state.js";

export type Checked<T> = { value: T | null; errors: Issue[]; warnings: Issue[] };

export type StructuredCall<T> = {
  model: BaseChatModel;
  role: CallRecord["role"];
  system: string;
  message: string;
  tool: { name: string; description: string; schema: z.ZodType };
  /** Parse and check the tool's arguments; `value` is null when the structure is unusable. */
  check: (args: unknown) => Checked<T>;
  /** Keep the usable part of the last structurally valid reply, or null. */
  fallback: (last: T, errors: Issue[]) => T | null;
  /** Replies checked in total, the first included. */
  maxAttempts?: number;
  /** List fields that may come back as one string: ID lists are split, text lists wrapped. */
  lists?: ListFields;
};

export type ListFields = { ids: readonly string[]; texts: readonly string[] };

export type CallOutcome<T> = { value: T | null; accepted: boolean; fallback: boolean; calls: CallRecord[] };

function pathOf(path: readonly PropertyKey[]): string {
  return path.reduce<string>((out, key) => (typeof key === "number" ? `${out}[${key}]` : out ? `${out}.${String(key)}` : String(key)), "");
}

/** zod issues as numbered-error entries. */
export function zodIssues(error: z.ZodError, code = "schema"): Issue[] {
  return error.issues.map((i) => ({ code, path: pathOf(i.path), message: i.message }));
}

export function submitTool(name: string, description: string, schema: z.ZodType): FunctionTool {
  const parameters = apiJsonSchema(schema);
  return { type: "function", strict: false, function: { name, description, parameters, strict: false } };
}

export function retryMessage(message: string, previous: string, errors: Issue[]): string {
  const list = errors.map((e, i) => `${i + 1}. ${e.path ? `${e.path}: ` : ""}${e.message}`).join("\n");
  return `${message}\n<previous_reply>\n${previous}\n</previous_reply>\n<validation_errors>\n${list}\n</validation_errors>\nCorrect exactly the listed errors, change nothing else, and call the tool again with the whole corrected reply.`;
}

/**
 * Decode values the model sent as JSON text inside the tool arguments, such as an
 * array passed as the string "[...]". Haiku did this in live test round 4
 * (2026-10-20), and the schema check then rejected the whole reply. Returns the
 * decoded arguments and the paths that were decoded.
 */
export function decodeNested(args: unknown, path = ""): { value: unknown; decoded: string[] } {
  if (typeof args === "string") {
    const text = args.trim();
    if ((text.startsWith("[") && text.endsWith("]")) || (text.startsWith("{") && text.endsWith("}"))) {
      try {
        const parsed = JSON.parse(text) as unknown;
        if (parsed && typeof parsed === "object") {
          const inner = decodeNested(parsed, path);
          return { value: inner.value, decoded: [path || "(root)", ...inner.decoded] };
        }
      } catch {
        // Not JSON: an ordinary string that happens to start with a bracket.
      }
    }
    return { value: args, decoded: [] };
  }
  if (Array.isArray(args)) {
    const items = args.map((x, i) => decodeNested(x, `${path}[${i}]`));
    return { value: items.map((x) => x.value), decoded: items.flatMap((x) => x.decoded) };
  }
  if (args && typeof args === "object") {
    const entries = Object.entries(args).map(([k, v]) => [k, decodeNested(v, path ? `${path}.${k}` : k)] as const);
    return { value: Object.fromEntries(entries.map(([k, x]) => [k, x.value])), decoded: entries.flatMap(([, x]) => x.decoded) };
  }
  return { value: args, decoded: [] };
}

/**
 * Turn a string sent where the schema expects a list into a list: `"side_b": "A2"` becomes
 * `["A2"]`, and an ID list sent as "r1-b1-f6, r1-b1-f8" is split. In the Lab 4 telescope run
 * (2026-10-26) one such string cost a retry that resent the whole input. Returns the paths changed.
 */
export function wrapLists(args: unknown, fields: ListFields, path = ""): { value: unknown; wrapped: string[] } {
  if (Array.isArray(args)) {
    const items = args.map((x, i) => wrapLists(x, fields, `${path}[${i}]`));
    return { value: items.map((x) => x.value), wrapped: items.flatMap((x) => x.wrapped) };
  }
  if (!args || typeof args !== "object") return { value: args, wrapped: [] };
  const wrapped: string[] = [];
  const entries = Object.entries(args).map(([k, v]) => {
    const at = path ? `${path}.${k}` : k;
    if (typeof v === "string" && (fields.ids.includes(k) || fields.texts.includes(k))) {
      wrapped.push(at);
      const list = fields.ids.includes(k) ? v.split(/[\s,;]+/) : [v];
      return [k, list.map((s) => s.trim()).filter(Boolean)] as const;
    }
    const inner = wrapLists(v, fields, at);
    wrapped.push(...inner.wrapped);
    return [k, inner.value] as const;
  });
  return { value: Object.fromEntries(entries), wrapped };
}

export async function structuredCall<T>(call: StructuredCall<T>): Promise<CallOutcome<T>> {
  const maxAttempts = call.maxAttempts ?? 2;
  const model = call.model.bindTools!([submitTool(call.tool.name, call.tool.description, call.tool.schema)]) as Runnable<BaseMessage[], AIMessage>;
  const system = new SystemMessage(call.system);
  const calls: CallRecord[] = [];
  let message = call.message;
  let last: Checked<T> | null = null;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const t0 = Date.now();
    const ai = await model.invoke([system, new HumanMessage(message)]);
    const toolCall = (ai.tool_calls ?? []).find((c) => c.name === call.tool.name);
    const decoded = toolCall ? decodeNested(toolCall.args) : { value: null, decoded: [] };
    const listed = toolCall && call.lists ? wrapLists(decoded.value, call.lists) : { value: decoded.value, wrapped: [] };
    const checked: Checked<T> = toolCall
      ? call.check(listed.value)
      : { value: null, errors: [{ code: "no_reply", path: "", message: `the reply did not call ${call.tool.name}` }], warnings: [] };
    if (decoded.decoded.length) {
      checked.warnings = [...checked.warnings, { code: "decoded_json_text", path: decoded.decoded.join(", "), message: "a value sent as JSON text was decoded" }];
    }
    if (listed.wrapped.length) {
      checked.warnings = [...checked.warnings, { code: "wrapped_list", path: listed.wrapped.join(", "), message: "a single value sent where a list is expected was made a list" }];
    }
    if (checked.value !== null) last = checked;
    const accepted = checked.value !== null && checked.errors.length === 0;
    const reply = toolCall ? JSON.stringify(toolCall.args) : textOf(ai);
    calls.push({
      role: call.role,
      attempt,
      accepted,
      errors: checked.errors,
      warnings: checked.warnings,
      input: message,
      reply,
      ...usageOf(ai),
      ms: Date.now() - t0,
    });
    if (accepted) return { value: checked.value, accepted: true, fallback: false, calls };
    message = retryMessage(call.message, reply, checked.errors);
  }

  const value = last?.value != null ? call.fallback(last.value, last.errors) : null;
  return { value, accepted: false, fallback: value !== null, calls };
}
