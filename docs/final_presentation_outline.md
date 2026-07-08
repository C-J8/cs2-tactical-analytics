# Presentation Outline -- CS2 Tactical Analytics MVP

## Slide 1 -- Title
- title: Title
- objective: Introduce the MVP.
- bullet points: CS2 Tactical Analytics; Vitality Mirage; offline-first pipeline
- suggested table/figure: Project title and scope
- speaker note: Frame the work as an MVP, not a product.

## Slide 2 -- Problem and motivation
- title: Problem and motivation
- objective: Explain why tactical data needs structure.
- bullet points: Demos are rich but hard to compare; manual review needs prioritization
- suggested table/figure: Pipeline diagram
- speaker note: Emphasize analyst workflow.

## Slide 3 -- Scope
- title: Scope
- objective: Set boundaries.
- bullet points: Vitality T-side Mirage; planted A/B only; no CT-side/no-plant model
- suggested table/figure: Scope table
- speaker note: Boundaries protect interpretation.

## Slide 4 -- Data pipeline
- title: Data pipeline
- objective: Show how raw demos become features.
- bullet points: Catalog; archives; parsing; quality; features; state; modeling
- suggested table/figure: Lineage table
- speaker note: Point to auditability.

## Slide 5 -- Dataset snapshot
- title: Dataset snapshot
- objective: Summarize sample size.
- bullet points: Demos; T rounds; planted rounds; A/B balance
- suggested table/figure: Dataset snapshot table
- speaker note: Mention class imbalance.

## Slide 6 -- Tactical EDA
- title: Tactical EDA
- objective: Show descriptive analysis layer.
- bullet points: Region, utility, no-plant, progression summaries
- suggested table/figure: EDA overview
- speaker note: No causal claims.

## Slide 7 -- Key findings
- title: Key findings
- objective: Present candidate patterns.
- bullet points: Top ranked associations require demo review
- suggested table/figure: Top findings table
- speaker note: Language should stay conservative.

## Slide 8 -- Modeling task
- title: Modeling task
- objective: Define label and exclusions.
- bullet points: High-confidence T-side planted A/B only
- suggested table/figure: Target definition
- speaker note: No-plant is separate.

## Slide 9 -- Baseline model
- title: Baseline model
- objective: Explain Stage 6.
- bullet points: Leakage-controlled CV; horizon filters; baseline comparison
- suggested table/figure: Baseline metrics
- speaker note: Avoid production claims.

## Slide 10 -- Error analysis
- title: Error analysis
- objective: Explain what failed.
- bullet points: B-predicted-as-A remained important
- suggested table/figure: Error summary
- speaker note: Motivates refinement.

## Slide 11 -- Refined candidate
- title: Refined candidate
- objective: Show selected candidate.
- bullet points: 35s stable_only logistic_regression
- suggested table/figure: Candidate summary
- speaker note: Chosen for B behavior improvement.

## Slide 12 -- Candidate model card
- title: Candidate model card
- objective: State decision and cautions.
- bullet points: Exploratory candidate; manual review pending
- suggested table/figure: Model card excerpt
- speaker note: Be explicit about limitations.

## Slide 13 -- Limitations
- title: Limitations
- objective: Make risks visible.
- bullet points: Small sample; lower B support; no external validation
- suggested table/figure: Limitations table
- speaker note: This builds trust.

## Slide 14 -- Next steps
- title: Next steps
- objective: Give a practical roadmap.
- bullet points: Manual review; inspect errors; temporal split; expand scope
- suggested table/figure: Next steps table
- speaker note: Sequence matters.

## Slide 15 -- Closing
- title: Closing
- objective: Summarize value.
- bullet points: Auditable offline pipeline and candidate report pack
- suggested table/figure: Final summary
- speaker note: Close with what is ready now.
