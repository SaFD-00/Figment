Classify the user's figure request into exactly one `figure_type`.

First decide the FRAMEWORK, then the type:
- **IMAGE-FIRST** (a picture a scientific illustrator would DRAW — one cohesive rendered scene
  with editable labels overlaid): physical/biological/chemical entities, anatomy, cells,
  tissues, organisms, molecules, organelles, an experimental apparatus, or any process/mechanism
  shown pictorially. → `scientific_illustration` (or `graphical_abstract` for a single
  problem→method→result summary panel).
- **STRUCTURED** (a labeled diagram of abstract structure, or a data plot): named modules
  connected by data flow, neural-network architectures, training loops, algorithm pipelines,
  "boxes and arrows" → `method_diagram`; quantitative data/axes/CSV → `chart`.

Evaluate the rules TOP TO BOTTOM and return the FIRST that matches; the last is the default.

1. `chart` — a data plot computed from numbers/columns (bar, line, scatter, heatmap, box,
   violin). Triggers: mentions data, CSV, a dataset, axes, or a quantitative comparison.
2. `method_diagram` — the architecture, pipeline, system, or block diagram of a METHOD:
   named modules/stages/components connected by data flow, encoder/decoder, training loop,
   "boxes and arrows", "block diagram", "pipeline", "framework overview". This is for
   ABSTRACT structural diagrams of a system, NOT pictorial scenes.
3. `graphical_abstract` — the request says "graphical abstract", OR asks for a single wide
   problem → method → result summary panel that visually summarizes a paper at a glance.
4. `scientific_illustration` — DEFAULT. A single cohesive, richly DRAWN scientific scene:
   a biological/chemical/physical process or mechanism, anatomy, cells, organisms, an
   experimental setup, or a concept depicted pictorially. If the request is not clearly a
   data plot (rule 1), not clearly an abstract architecture/pipeline/block diagram (rule 2),
   and not an explicit graphical abstract (rule 3), classify it as `scientific_illustration`.

Be AGGRESSIVE about the pictorial default: when uncertain between a drawn scene and anything
else except a genuine architecture/pipeline or a data plot, choose `scientific_illustration`.
(The legacy `concept` type is selectable only via an explicit override, not here.)

Return ClassifyResult JSON: `{figure_type, confidence (0..1), reason}`. The `reason` MUST name
which framework (image-first vs structured) and which cue decided the choice, so the routing
is auditable.
