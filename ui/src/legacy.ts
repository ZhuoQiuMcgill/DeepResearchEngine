// Keep existing local workflows and run history while updating old UI copy.
const replacements = [
  ["Evidence to insight", "INSE 691 Project"],
  ["Conflict checker", "Organizer"],
  ["conflict checker", "organizer"],
  ["Extract evidence with provenance", "Collect key points from pages"],
  ["Surface contradictions & assumptions", "Organize notes by topic"],
  [
    "Synthesize findings and cite evidence",
    "Turn research notes into a report",
  ],
  [
    "How can environment-based design improve the reliability of AI research?",
    "How can environment-based design guide an AI research workflow?",
  ],
  [
    "Draft placeholder: real findings and citations will arrive from the research backend.",
    "Report placeholder: content will arrive from the research backend.",
  ],
];
export function migrateLegacy<T>(value: T): T {
  if (typeof value === "string") {
    return replacements.reduce<string>(
      (text, [before, after]) => text.split(before).join(after),
      value,
    ) as T;
  }
  if (Array.isArray(value)) return value.map(migrateLegacy) as T;
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, migrateLegacy(item)]),
    ) as T;
  }
  return value;
}
