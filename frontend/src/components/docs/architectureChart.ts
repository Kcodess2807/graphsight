// The full Graphsight architecture diagram — kept verbatim from the README's
// §II "Architecture & Stack" Mermaid so the two never drift. Rendered + animated
// by <MermaidDiagram>. Swap this string to show a different diagram.
export const ARCHITECTURE_CHART = `flowchart TB
  %% ---------- 1 INGESTION ----------
  subgraph INGEST["1 · Ingestion pipeline (offline CLI)"]
    direction TB
    DOC["Source doc<br/>'PR #N merged by AUTHOR. Title… Description…'"]
    DOC --> WIN["sliding_window_words<br/>300-word windows · 50 overlap"]
    WIN --> NER["GLiNER zero-shot NER<br/>Person · Service · Library · PR<br/>Ticket · Team · Tool<br/>(spaCy ruler fallback)"]
    NER --> MEMB["embed each mention<br/>MiniLM · 384-dim · normalized"]
    MEMB --> CUR1{"cosine vs<br/>existing nodes"}
    CUR1 -->|"≥ 0.92"| FAST["fast auto-merge<br/>0 LLM"]
    CUR1 -->|"0.85 – 0.92"| DEEP["Groq · same entity?<br/>YES / NO · fail-safe NO"]
    CUR1 -->|"under 0.85"| NEW["mint new node<br/>slug id"]
    DEEP -->|YES| FAST
    DEEP -->|NO| NEW
  end

  %% ---------- 2 HYBRID STORE ----------
  subgraph SCHEMA["2 · LadybugDB — single .lbug (vectors + graph)"]
    direction LR
    ENT[("Entity<br/>id · label · type<br/>embedding FLOAT 384")]
    DOCN[("Document<br/>id · path · content")]
    ENT -->|"RELATES_TO · confidence"| ENT
    DOCN -->|MENTIONS| ENT
    HNSW["HNSW vector index<br/>on Entity.embedding"]
    ENT --- HNSW
  end
  FAST --> ENT
  NEW --> ENT
  MEMB -. "document + edges" .-> DOCN

  %% ---------- 3 QUERY ----------
  Q(["User query"]) --> IC["classify_intent"]
  IC -->|"keyword markers"| W["alpha / beta weights"]
  IC -->|"ambiguous"| GROQI["Groq · SEMANTIC / RELATIONAL"]
  GROQI --> W

  subgraph VEC["3a · Vector arm — semantic"]
    direction TB
    QE["embed_query · MiniLM"] --> VS["QUERY_VECTOR_INDEX (HNSW)<br/>top-k pool · similarity s_v"]
  end

  subgraph GRAPH["3b · Graph arm — relational"]
    direction TB
    SEEDL["linked seeds<br/>spaCy ruler → find_nodes_by_label"]
    SEEDF["fuzzy seeds<br/>cosine ≥ 0.35 · top-3"]
    SEEDL --> SD["seed set · dedup"]
    SEEDF --> SD
    SD --> EF["expand_frontier<br/>ONE query per hop · no N+1"]
    EF --> HUB["hub throttle<br/>skip degree above MAX_DEGREE"]
    HUB --> PS["path_score =<br/>product of edge confidences"]
    PS --> HOPQ{"hop below MAX_HOPS<br/>and frontier left?"}
    HOPQ -->|yes| EF
    HOPQ -->|no| GG["graph_scores s_g + hops"]
  end

  W --> QE
  W --> SEEDL
  VS --> SEEDF
  QE -. reads .-> HNSW
  VS -. reads .-> ENT
  EF -. traverses .-> ENT

  VS --> FUSE["Fusion · S = alpha·s_v + beta·s_g<br/>dynamic vector_k throttle by graph hits<br/>rank → top_k nodes"]
  GG --> FUSE
  FUSE --> AD["attach_documents · via MENTIONS"]
  AD -. reads .-> DOCN
  AD --> BC["build_context<br/>dedup chunks · graph traces first"]
  BC --> GEN["Grounded generation<br/>OpenRouter · context-only · streamed"]
  GEN --> OUT(["answer + per-node score pills<br/>+ trace_log → ReactFlow canvas"])
`;
