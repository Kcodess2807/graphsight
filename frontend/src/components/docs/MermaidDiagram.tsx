import { useEffect, useRef, useState } from "react";

let mermaidReady = false;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function ensureMermaid(mermaid: any) {
  if (mermaidReady) return;
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: "loose", // allow the <br/> html labels in the chart
    theme: "base",
    flowchart: { htmlLabels: true, curve: "basis", padding: 14 },
    themeVariables: {
      fontFamily: "ui-sans-serif, system-ui, sans-serif",
      fontSize: "13px",
      primaryColor: "#eef2ff",
      primaryBorderColor: "#c7d2fe",
      primaryTextColor: "#312e81",
      lineColor: "#a5b4fc",
      clusterBkg: "#fbfbff",
      clusterBorder: "#e0e7ff",
    },
  });
  mermaidReady = true;
}

let renderSeq = 0;

// Hide every drawable piece so the reveal can fade/draw it back in.
function prepHidden(svg: SVGSVGElement) {
  svg.querySelectorAll<SVGGElement>(".node, .cluster").forEach((n) => {
    n.style.opacity = "0";
  });
  svg.querySelectorAll<SVGPathElement>(".edgePaths path").forEach((e) => {
    const len = typeof e.getTotalLength === "function" ? e.getTotalLength() : 0;
    if (len > 0) {
      e.style.strokeDasharray = String(len);
      e.style.strokeDashoffset = String(len);
    } else {
      e.style.opacity = "0";
    }
  });
  svg
    .querySelectorAll<SVGElement>(".edgeLabel, marker path, .arrowheadPath")
    .forEach((m) => {
      m.style.opacity = "0";
    });
}

// Sequential reveal: nodes fade in, then edges draw themselves, then labels.
// NOTE: nodes are positioned via a transform attribute, so we only animate
// opacity on them — a CSS transform would clobber their placement.
function playReveal(svg: SVGSVGElement) {
  const nodes = Array.from(svg.querySelectorAll<SVGGElement>(".node, .cluster"));
  const edges = Array.from(svg.querySelectorAll<SVGPathElement>(".edgePaths path"));
  const labels = Array.from(svg.querySelectorAll<SVGElement>(".edgeLabel"));

  const STEP = 65;
  nodes.forEach((n, i) => {
    n.style.animation = "mm-fade 0.45s ease forwards";
    n.style.animationDelay = `${i * STEP}ms`;
  });

  const afterNodes = nodes.length * STEP + 120;
  edges.forEach((e, i) => {
    const drawn = e.style.strokeDasharray && e.style.strokeDasharray !== "0";
    e.style.animation = `${drawn ? "mm-draw" : "mm-fade"} 0.5s ease forwards`;
    e.style.animationDelay = `${afterNodes + i * 28}ms`;
  });

  const tail = afterNodes + edges.length * 28;
  svg
    .querySelectorAll<SVGElement>("marker path, .arrowheadPath")
    .forEach((m) => {
      m.style.animation = "mm-fade 0.3s ease forwards";
      m.style.animationDelay = `${tail}ms`;
    });
  labels.forEach((l, i) => {
    l.style.animation = "mm-fade 0.35s ease forwards";
    l.style.animationDelay = `${tail + i * 22}ms`;
  });
}

export function MermaidDiagram({ chart }: { chart: string }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const ioRef = useRef<IntersectionObserver | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      // lazy-load mermaid so its (large) bundle only ships on this docs page
      const mermaid = (await import("mermaid")).default;
      if (cancelled) return;
      ensureMermaid(mermaid);
      const id = `mmd-${renderSeq++}`;
      const { svg } = await mermaid.render(id, chart);
      if (cancelled || !hostRef.current) return;

      hostRef.current.innerHTML = svg;
      const svgEl = hostRef.current.querySelector("svg") as SVGSVGElement | null;
      if (!svgEl) return;
      svgEl.style.maxWidth = "100%";
      svgEl.style.height = "auto";

      const reduce = window.matchMedia?.(
        "(prefers-reduced-motion: reduce)"
      ).matches;
      if (reduce) return; // honor reduced motion: show the diagram, no animation

      prepHidden(svgEl);
      ioRef.current = new IntersectionObserver(
        (entries, obs) => {
          entries.forEach((en) => {
            if (en.isIntersecting) {
              playReveal(svgEl);
              obs.disconnect();
            }
          });
        },
        { threshold: 0.15 }
      );
      ioRef.current.observe(hostRef.current);
    })().catch(() => !cancelled && setError(true));

    return () => {
      cancelled = true;
      ioRef.current?.disconnect();
    };
  }, [chart]);

  if (error) {
    return (
      <div className="not-prose rounded-xl border border-amber-200 bg-amber-50/60 p-4 text-sm text-amber-800">
        Couldn’t render the architecture diagram.
      </div>
    );
  }

  return (
    <div className="not-prose overflow-x-auto rounded-2xl border border-border bg-white p-4 shadow-soft sm:p-6">
      <div ref={hostRef} className="mermaid-host min-w-[680px]" />
    </div>
  );
}
