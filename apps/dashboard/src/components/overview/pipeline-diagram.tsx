"use client";

import { motion, useReducedMotion } from "motion/react";

type NodeId = "diff" | "planner" | "plan" | "base" | "head" | "oracle" | "verdict";
type Orientation = "horizontal" | "vertical";

interface NodeSpec {
  id: NodeId;
  step: string;
  title: string;
  detail: string;
  /** Column in the pipeline; drives the draw-in order. */
  stage: number;
}

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface Layout {
  width: number;
  height: number;
  boxes: Record<NodeId, Box>;
}

const NODES: readonly NodeSpec[] = [
  { id: "diff", step: "01", title: "PR diff", detail: "base..head", stage: 0 },
  { id: "planner", step: "02", title: "Planner", detail: "proposes attacks", stage: 1 },
  { id: "plan", step: "03", title: "Frozen plan", detail: "9f2c…e41a", stage: 2 },
  { id: "base", step: "04", title: "Base env", detail: "isolated · ×2", stage: 3 },
  { id: "head", step: "04", title: "Head env", detail: "isolated · ×2", stage: 3 },
  { id: "oracle", step: "05", title: "Oracle", detail: "independent check", stage: 4 },
  { id: "verdict", step: "06", title: "Verdict", detail: "regression", stage: 5 },
];

const EDGES: readonly [NodeId, NodeId][] = [
  ["diff", "planner"],
  ["planner", "plan"],
  ["plan", "base"],
  ["plan", "head"],
  ["base", "oracle"],
  ["head", "oracle"],
  ["oracle", "verdict"],
];

/** The path the traveling pulse follows: the head branch, where the regression shows up. */
const PULSE_ROUTE: readonly NodeId[] = ["diff", "planner", "plan", "head", "oracle", "verdict"];

const NODE_W = 128;
const NODE_H = 60;

const HORIZONTAL: Layout = {
  width: 1000,
  height: 236,
  boxes: {
    diff: { x: 0.5, y: 88, w: NODE_W, h: NODE_H },
    planner: { x: 168, y: 88, w: NODE_W, h: NODE_H },
    plan: { x: 336, y: 88, w: NODE_W, h: NODE_H },
    base: { x: 504, y: 8, w: NODE_W, h: NODE_H },
    head: { x: 504, y: 168, w: NODE_W, h: NODE_H },
    oracle: { x: 672, y: 88, w: NODE_W, h: NODE_H },
    verdict: { x: 840, y: 82, w: 159.5, h: 72 },
  },
};

const V_W = 168;
const VERTICAL: Layout = {
  width: 360,
  height: 604,
  boxes: {
    diff: { x: 96, y: 0.5, w: V_W, h: NODE_H },
    planner: { x: 96, y: 96, w: V_W, h: NODE_H },
    plan: { x: 96, y: 192, w: V_W, h: NODE_H },
    base: { x: 8, y: 300, w: 160, h: NODE_H },
    head: { x: 192, y: 300, w: 160, h: NODE_H },
    oracle: { x: 96, y: 408, w: V_W, h: NODE_H },
    verdict: { x: 80, y: 508, w: 200, h: 72 },
  },
};

function edgePath(a: Box, b: Box, orientation: Orientation): string {
  if (orientation === "horizontal") {
    const x1 = a.x + a.w;
    const y1 = a.y + a.h / 2;
    const x2 = b.x;
    const y2 = b.y + b.h / 2;
    const mid = (x1 + x2) / 2;
    return `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`;
  }
  const x1 = a.x + a.w / 2;
  const y1 = a.y + a.h;
  const x2 = b.x + b.w / 2;
  const y2 = b.y;
  const mid = (y1 + y2) / 2;
  return `M ${x1} ${y1} C ${x1} ${mid}, ${x2} ${mid}, ${x2} ${y2}`;
}

/** One continuous path through node centers, so the pulse never jumps. */
function routePath(layout: Layout, orientation: Orientation): string {
  const center = (b: Box): [number, number] => [b.x + b.w / 2, b.y + b.h / 2];
  const boxes = PULSE_ROUTE.map((id) => layout.boxes[id]);
  const [sx, sy] = center(layout.boxes.diff);
  let d = `M ${sx} ${sy}`;
  for (const [i, b] of boxes.entries()) {
    const a = boxes[i - 1];
    if (!a) continue;
    const edge = edgePath(a, b, orientation).replace(/^M [^C]+/, "");
    const start = orientation === "horizontal" ? [a.x + a.w, a.y + a.h / 2] : [a.x + a.w / 2, a.y + a.h];
    const [cx, cy] = center(b);
    d += ` L ${start[0]} ${start[1]} ${edge} L ${cx} ${cy}`;
  }
  return d;
}

const EASE: [number, number, number, number] = [0.16, 1, 0.3, 1];
const STAGE_DELAY = 0.28;

function Node({ spec, box, reduce }: { spec: NodeSpec; box: Box; reduce: boolean }) {
  const isVerdict = spec.id === "verdict";
  const isPlan = spec.id === "plan";
  const delay = 0.1 + spec.stage * STAGE_DELAY;
  return (
    <motion.g
      initial={reduce ? false : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: EASE, delay }}
    >
      <rect
        x={box.x}
        y={box.y}
        width={box.w}
        height={box.h}
        rx={9}
        className={
          isVerdict ? "fill-[oklch(0.19_0.03_24)] stroke-regression/60" : "fill-card stroke-foreground/[0.14]"
        }
        strokeWidth={1}
      />
      <text
        x={box.x + 14}
        y={box.y + 21}
        className={isVerdict ? "fill-regression/80" : "fill-muted-foreground/70"}
        style={{ font: "500 9.5px var(--font-mono)", letterSpacing: "0.06em" }}
      >
        {spec.step}
      </text>
      <text
        x={box.x + 34}
        y={box.y + 21}
        className="fill-foreground"
        style={{ font: "500 12.5px var(--font-sans)", letterSpacing: "-0.005em" }}
      >
        {spec.title}
      </text>
      {isVerdict ? (
        <g>
          <circle cx={box.x + 18} cy={box.y + 47} r={3} className="fill-regression" />
          <text
            x={box.x + 28}
            y={box.y + 51}
            className="fill-regression"
            style={{ font: "500 12px var(--font-sans)" }}
          >
            regression
          </text>
          <text
            x={box.x + box.w - 14}
            y={box.y + 51}
            textAnchor="end"
            className="fill-muted-foreground"
            style={{ font: "400 10px var(--font-mono)" }}
          >
            head 2/2
          </text>
        </g>
      ) : (
        <text
          x={box.x + (isPlan ? 30 : 14)}
          y={box.y + 43}
          className={isPlan ? "fill-foreground/85" : "fill-muted-foreground"}
          style={{ font: "400 10.5px var(--font-mono)" }}
        >
          {spec.detail}
        </text>
      )}
      {isPlan && (
        <g className="stroke-muted-foreground" fill="none" strokeWidth={1.1} strokeLinecap="round" strokeLinejoin="round">
          <rect x={box.x + 14} y={box.y + 35.5} width={9} height={7} rx={1.5} />
          <path d={`M ${box.x + 16.25} ${box.y + 35.5} v -2 a 2.25 2.25 0 0 1 4.5 0 v 2`} />
        </g>
      )}
    </motion.g>
  );
}

function Diagram({ layout, orientation, reduce }: { layout: Layout; orientation: Orientation; reduce: boolean }) {
  const route = routePath(layout, orientation);
  const stageOf = (id: NodeId): number => NODES.find((n) => n.id === id)?.stage ?? 0;
  const drawDone = 0.1 + 5 * STAGE_DELAY + 0.4;
  return (
    <svg
      viewBox={`-1 -1 ${layout.width + 2} ${layout.height + 2}`}
      className="h-auto w-full overflow-visible"
      role="img"
      aria-labelledby={`pipeline-title-${orientation}`}
    >
      <title id={`pipeline-title-${orientation}`}>
        Gate pipeline: the PR diff goes to the planner, which proposes a plan that is hashed and frozen. The plan runs on
        base and head environments, an independent oracle compares them, and the verdict reports a regression.
      </title>
      <g fill="none" strokeWidth={1.25} strokeLinecap="round">
        {EDGES.map(([from, to]) => {
          const toVerdict = to === "verdict";
          return (
            <motion.path
              key={`${from}-${to}`}
              d={edgePath(layout.boxes[from], layout.boxes[to], orientation)}
              className={toVerdict ? "stroke-regression/50" : "stroke-foreground/25"}
              initial={reduce ? false : { pathLength: 0, opacity: 0 }}
              animate={{ pathLength: 1, opacity: 1 }}
              transition={{ duration: 0.55, ease: "easeInOut", delay: 0.2 + stageOf(from) * STAGE_DELAY }}
            />
          );
        })}
      </g>
      {!reduce && (
        <motion.g initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: drawDone, duration: 0.4 }}>
          <circle r={7} className="fill-foreground/10">
            <animateMotion dur="5.5s" repeatCount="indefinite" path={route} begin={`${drawDone}s`} />
          </circle>
          <circle r={2.4} className="fill-foreground">
            <animateMotion dur="5.5s" repeatCount="indefinite" path={route} begin={`${drawDone}s`} />
          </circle>
        </motion.g>
      )}
      {NODES.map((spec) => (
        <Node key={spec.id} spec={spec} box={layout.boxes[spec.id]} reduce={reduce} />
      ))}
    </svg>
  );
}

/** Animated Gate pipeline. Horizontal on wide screens, stacked on phones. */
export function PipelineDiagram() {
  const reduce = useReducedMotion() ?? false;
  return (
    <>
      <div className="hidden md:block">
        <Diagram layout={HORIZONTAL} orientation="horizontal" reduce={reduce} />
      </div>
      <div className="mx-auto max-w-[360px] md:hidden">
        <Diagram layout={VERTICAL} orientation="vertical" reduce={reduce} />
      </div>
    </>
  );
}
