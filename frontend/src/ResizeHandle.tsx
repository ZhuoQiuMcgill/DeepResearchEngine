import type { PointerEvent } from "react";
export function ResizeHandle({
  label,
  value,
  min,
  max,
  onChange,
  horizontal = false,
  reverse = false,
  onReset,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
  horizontal?: boolean;
  reverse?: boolean;
  onReset: () => void;
}) {
  const clamp = (n: number) => Math.round(Math.max(min, Math.min(max, n)));
  function begin(e: PointerEvent<HTMLDivElement>) {
    if (e.button !== 0) return;
    e.preventDefault();
    const target = e.currentTarget;
    target.setPointerCapture(e.pointerId);
    const start = horizontal ? e.clientY : e.clientX;
    const move = (event: globalThis.PointerEvent) =>
      onChange(
        clamp(
          value +
            ((horizontal ? event.clientY : event.clientX) - start) *
              (reverse ? -1 : 1),
        ),
      );
    const finish = () => {
      target.removeEventListener("pointermove", move);
      target.removeEventListener("lostpointercapture", finish);
      target.removeEventListener("pointerup", finish);
      target.removeEventListener("pointercancel", finish);
    };
    target.addEventListener("pointermove", move);
    target.addEventListener("pointerup", finish);
    target.addEventListener("pointercancel", finish);
    target.addEventListener("lostpointercapture", finish);
  }
  return (
    <div
      className={`resize-divider ${horizontal ? "horizontal" : "vertical"}`}
      role="separator"
      aria-label={label}
      aria-orientation={horizontal ? "horizontal" : "vertical"}
      aria-valuenow={value}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      title={`${label} · Drag to resize · Double-click to reset`}
      onPointerDown={begin}
      onDoubleClick={onReset}
      onKeyDown={(e) => {
        const negative = horizontal ? "ArrowUp" : "ArrowLeft",
          positive = horizontal ? "ArrowDown" : "ArrowRight";
        if (e.key === negative || e.key === positive) {
          e.preventDefault();
          onChange(
            clamp(value + (e.key === positive ? 20 : -20) * (reverse ? -1 : 1)),
          );
        }
        if (e.key === "Home") {
          e.preventDefault();
          onReset();
        }
      }}
    />
  );
}
