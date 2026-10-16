"use client";

import "@xyflow/react/dist/base.css";

import {
  Background,
  BackgroundVariant,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { Brain, FileText, Scale } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";

import { TONE_CLASSES, toneOf } from "@/components/shared";
import type { CounterfactualCase } from "@/lib/gauntlet";
import { cn } from "@/lib/utils";

import { EXPOSURE_LABEL, NODE_KIND_LABELS } from "./model";

const COL_X = { trigger: 0, memory: 330, decision: 700 } as const;
const ROW_H = 88;
const GROUP_GAP = 28;
const FIT_PADDING = 0.12;
const EDGE_COLOR = { neutral: "oklch(1 0 0 / 22%)", tainted: "var(--regression)" } as const;

interface SourceData extends Record<string, unknown> {
  id: string;
  kind: string;
  caption: string;
  tainted: boolean;
}
interface DecisionData extends Record<string, unknown> {
  id: string;
  classification: string;
  exposure: string;
  selected: boolean;
}
type SourceNode = Node<SourceData, "source">;
type DecisionNode = Node<DecisionData, "decision">;

const HIDDEN_HANDLE = "!size-1 !min-w-0 !min-h-0 !border-0 !bg-transparent";

function SourceNodeView({ data }: NodeProps<SourceNode>) {
  const Icon = data.kind === "memory" ? Brain : FileText;
  return (
    <div
      className={cn(
        "bg-card w-[188px] rounded-lg border px-3 py-2.5 shadow-sm",
        data.tainted ? "border-regression/40" : "border-border",
      )}
    >
      {data.kind === "memory" && <Handle type="target" position={Position.Left} className={HIDDEN_HANDLE} />}
      <div className="text-muted-foreground flex items-center gap-1.5 text-[10px] font-medium tracking-wide uppercase">
        <Icon className="size-3" aria-hidden />
        {NODE_KIND_LABELS[data.kind] ?? data.kind}
      </div>
      <div className="mt-1 font-mono text-sm font-medium">{data.id}</div>
      <div className="text-muted-foreground mt-0.5 text-[11px]">{data.caption}</div>
      <Handle type="source" position={Position.Right} className={HIDDEN_HANDLE} />
    </div>
  );
}

function DecisionNodeView({ data }: NodeProps<DecisionNode>) {
  const tone = TONE_CLASSES[toneOf(data.classification)];
  return (
    <div
      className={cn(
        "bg-card w-[200px] cursor-pointer rounded-lg border px-3 py-2.5 shadow-sm transition-colors",
        "hover:bg-accent",
        data.selected ? "border-foreground/60 ring-foreground/20 ring-2" : tone.border,
      )}
    >
      <Handle type="target" position={Position.Left} className={HIDDEN_HANDLE} />
      <div className="text-muted-foreground flex items-center justify-between text-[10px] font-medium tracking-wide uppercase">
        <span className="flex items-center gap-1.5">
          <Scale className="size-3" aria-hidden />
          Decision
        </span>
        <span>{data.exposure}</span>
      </div>
      <div className="mt-1 font-mono text-sm font-medium">{data.id}</div>
      <div className={cn("mt-0.5 flex items-center gap-1.5 text-[11px] font-medium", tone.text)}>
        <span className={cn("size-1.5 rounded-full", tone.dot)} aria-hidden />
        {data.classification.replaceAll("_", " ")}
      </div>
    </div>
  );
}

const NODE_TYPES = { source: SourceNodeView, decision: DecisionNodeView };

function edgeStyle(tainted: boolean): Pick<Edge, "animated" | "style" | "markerEnd" | "labelStyle" | "labelBgStyle"> {
  const stroke = tainted ? EDGE_COLOR.tainted : EDGE_COLOR.neutral;
  return {
    animated: tainted,
    style: { stroke, strokeWidth: tainted ? 1.5 : 1, strokeDasharray: tainted ? "5 4" : undefined },
    markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: stroke },
    labelStyle: { fill: tainted ? "var(--regression)" : "var(--muted-foreground)", fontSize: 10, fontWeight: 500 },
    labelBgStyle: { fill: "var(--background)" },
  };
}

function buildGraph(cases: readonly CounterfactualCase[], trigger: string, selected: string | null) {
  const direct = cases.filter((c) => c.exposure.direct);
  const second = cases.filter((c) => !c.exposure.direct);
  const memoryIds = [
    ...new Set(second.flatMap((c) => c.exposure.path.filter((e) => e.target.kind !== "decision").map((e) => e.target.node_id))),
  ];
  const ordered = [...direct, ...second];
  const yOf = (i: number) => i * ROW_H + (i >= direct.length ? GROUP_GAP : 0);
  const totalH = yOf(Math.max(ordered.length - 1, 0));
  const secondMid = second.length ? (yOf(direct.length) + yOf(ordered.length - 1)) / 2 : totalH / 2;

  const taintedMemory = new Set(
    second
      .filter((c) => c.verdict.classification === "tainted")
      .flatMap((c) => c.exposure.path.map((e) => e.target.node_id)),
  );

  const nodes: Node[] = [
    {
      id: trigger,
      type: "source",
      position: { x: COL_X.trigger, y: totalH / 2 },
      data: { id: trigger, kind: "document_chunk", caption: "Suspect source (trigger)", tainted: true },
    },
    ...memoryIds.map((m, i) => ({
      id: m,
      type: "source",
      position: { x: COL_X.memory, y: secondMid + i * ROW_H },
      data: { id: m, kind: "memory", caption: `Derived from ${trigger}`, tainted: taintedMemory.has(m) },
    })),
    ...ordered.map((c, i) => ({
      id: c.decision_id,
      type: "decision",
      position: { x: COL_X.decision, y: yOf(i) },
      data: {
        id: c.decision_id,
        classification: c.verdict.classification,
        exposure: c.exposure.direct ? EXPOSURE_LABEL.direct : EXPOSURE_LABEL.secondOrder,
        selected: selected === c.decision_id,
      },
    })),
  ];

  const edges = new Map<string, Edge>();
  for (const c of cases) {
    const tainted = c.verdict.classification === "tainted";
    for (const e of c.exposure.path) {
      const id = `${e.source.node_id}->${e.target.node_id}`;
      const prev = edges.get(id);
      const isTainted = tainted || (prev?.animated ?? false);
      const toDecision = e.target.kind === "decision";
      const label = toDecision ? (c.exposure.direct ? EXPOSURE_LABEL.direct : EXPOSURE_LABEL.secondOrder) : e.relation.replaceAll("_", " ");
      edges.set(id, { id, source: e.source.node_id, target: e.target.node_id, label, ...edgeStyle(isTainted) });
    }
  }
  return { nodes, edges: [...edges.values()] };
}

function Graph({
  cases,
  trigger,
  selected,
  onSelect,
}: {
  cases: readonly CounterfactualCase[];
  trigger: string;
  selected: string | null;
  onSelect: (decisionId: string) => void;
}) {
  const { nodes, edges } = useMemo(() => buildGraph(cases, trigger, selected), [cases, trigger, selected]);
  const { fitView } = useReactFlow();
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => void fitView({ padding: FIT_PADDING }));
    ro.observe(el);
    return () => ro.disconnect();
  }, [fitView]);

  return (
    <div ref={box} className="h-[460px] w-full min-w-[720px] sm:h-[560px]">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        fitView
        fitViewOptions={{ padding: FIT_PADDING }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        edgesFocusable={false}
        panOnDrag={false}
        panOnScroll={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        zoomOnDoubleClick={false}
        preventScrolling={false}
        minZoom={0.3}
        onNodeClick={(_, node) => {
          if (node.type === "decision") onSelect(node.id);
        }}
        aria-label={`Lineage from ${trigger} to exposed decisions`}
      >
        <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="oklch(1 0 0 / 7%)" />
      </ReactFlow>
    </div>
  );
}

export function LineageGraph(props: {
  cases: readonly CounterfactualCase[];
  trigger: string;
  selected: string | null;
  onSelect: (decisionId: string) => void;
}) {
  return (
    <ReactFlowProvider>
      <Graph {...props} />
    </ReactFlowProvider>
  );
}
